#!env/bin/python2.7
import time, sys, os, socket, ssl, stomp, logging, logging.config, requests, json, getpass, waitress, requests_futures
from requests_futures.sessions import FuturesSession
from flask import Flask, abort, request, json
from waitress import serve
from requests.auth import HTTPBasicAuth

SNOW_P_FROM_INPUT = getpass.getpass('ServiceNow password to send requests: ')

# Logging setup
def setup_logging(
    default_path='logging.json',
    default_level=logging.INFO,
    env_key='LOG_CFG'
):
    # Setup logging configuration
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

setup_logging()
logger = logging.getLogger(__name__)

# Test message to be sent to ServiceNow
'''
testMessageLink = {
    "eventTime": "2017-05-09T12:24:29.252+0000",
    "performer": {"userEmail": "draval@redhat.com", "userId": "draval@redhat.com.qa"},
    "caseNumber": "01825562",
    "caseStatus": "Waiting on Customer",
    "externalCaseUrl": "https://access.qa.redhat.com/support/cases/#/case/01825562",
    "internalCaseUrl": "https://gss--qa--c.cs60.visual.force.com/500A000000WlneZIAR",
    "caseSummary": "Hello,we have 3 RHEL 6.7 VMs,and we'd like to k",
    "action": "createIssueLink",
    "issueKey": "INC0486288"
}

testMessageLinkAck = {
    "linkStatus":"failed",
    "reason":"Unable to find case by number",
    "issueKey":"INC0486281",
    "caseNumber":"01111111",
    "eventTime":"2017-05-05T13:07:36.000Z",
    "action":"createCaseLinkAcknowledgement"
}

testMessageUnlink = {
    "eventTime": "2017-04-20T12:55:46.245+0000",
    "performer": {
        "userEmail": "dfisher@redhat.com",
        "userId": "dfisher@redhat.com.dfisher5"
    },
    "caseNumber": "01582900",
    "action": "removeIssueLink", 
    "issueKey": "INC0486248"
}

testMessageComment = {
  "performer" : {
    "userId" : "pbathia@redhat.com.qa",
    "userEmail" : "pbathia+qa@redhat.com"
  },
  "eventTime" : "2017-05-12T14:17:56.614+0000",
  "action" : "updateCase",
  "issueKeys" : ["INC0477720"],
  "caseSummary" : "RFE Portal - CC self to ticket on comment.",
  "caseStatus" : "Waiting on Customer",
  "caseNumber" : "00373076"
}

testMessageChangeStatus = {
  "performer" : {
    "userId" : "dfisher@redhat.com.qa",
    "userEmail" : "dfisher+support@redhat.com"
  },
  "eventTime" : "2017-05-02T15:14:00.510+0000",
  "action" : "updateCase",
  "issueKeys" : [ "INC0486278" ],
  "caseSummary" : "[satellite] [rfe] Ability to really lock a server from updates",
  "caseStatus" : "Waiting on Red Hat",
  "caseNumber" : "00337127"
}

testMessageChangeSummary = { 
    "eventTime": "2017-04-20T12:55:46.245+0000",
    "performer": {
        "userEmail": "dfisher@redhat.com",
        "userId": "dfisher@redhat.com.dfisher5"
    },
    "changedField": "summary",
    "changedValue": {
        "from": "We are not able open redhat sites",
        "to": "Changed: We are not able open redhat sites" 
    },
    "caseNumber": "01582900",
    "action": "updateIssue",
    "issueKey": "INC0486248"
}
'''

logger.info('Python: '+sys.version)

session = FuturesSession()
session.auth = HTTPBasicAuth('umb_listener_api', SNOW_P_FROM_INPUT)
session.verify = True
session.headers = {'Accept':'application/json', 'Content-Type':'application/json'}

# Setup connection incl. SSL
conn = stomp.Connection(
    # UMB DEV host
    #[('messaging-devops-broker01.dev1.ext.devlab.redhat.com', 61612), ('messaging-devops-broker02.dev1.ext.devlab.redhat.com', 61612)],

    # UMB QA host
    #[('messaging-devops-broker01.web.qa.ext.phx1.redhat.com', 61612), ('messaging-devops-broker02.web.qa.ext.phx1.redhat.com', 61612)],

    # UMB PROD host
    [('messaging-devops-broker01.web.prod.ext.phx2.redhat.com', 61612), ('messaging-devops-broker02.web.prod.ext.phx2.redhat.com', 61612)],

    # SSL Config
    use_ssl=True,
    ssl_key_file="servicenow.key",
    ssl_cert_file="servicenow.pem",
    ssl_ca_certs="RH-IT-Root-CA.pem",
    ssl_version=ssl.PROTOCOL_TLSv1_2,

    # Disconnect
    heartbeats=(10000, 10000),
    reconnect_attempts_max=10000
)



def connect_and_subscribe(conn):
    time.sleep(1)
    
    conn.start()
    
    # Assuming UMB dev environment
    conn.connect()
    logger.info('Connected to UMB!')
    
    # Subscribe to UMB queue
    conn.subscribe(destination='/queue/ticketing_to_servicenow', id='ticketing_to_servicenow', ack='auto')

# Setup stomp listener -> back to ServiceNow using requests.py
class MyListener(stomp.ConnectionListener):
    def __init__(self, conn):
        self.conn = conn

    def on_error(self, headers, message):
        logger.error('received an error "%s"' % message)

    def on_message(self, headers, message):
        logger.info('received a message')
        logger.debug('received a message "%s"' % message)

        session.post(
            'https://redhat.service-now.com/api/redha/umb_message/addMessage',
            json = json.loads(message)
        )

    def on_disconnected(self):
        logger.info('Disconnected')
        time.sleep(2)
        connect_and_subscribe(self.conn)

conn.set_listener('', MyListener(conn))
connect_and_subscribe(conn)

'''
# Test write access to UMB
#conn.send(body='test', destination='/queue/servicenow_to_ticketing')

# Test message to ServiceNow
requests.post(
    'https://redhatqa.service-now.com/api/redha/umb_message/addMessage',
    auth = HTTPBasicAuth('umb_listener', SNOW_P_FROM_INPUT),
    verify = True,
    json = testMessageComment,
    headers = {'Accept':'application/json', 'Content-Type':'application/json'}
)
'''

# TODO: resubscribe to cached subscriptions in case server is restarted

# Setup API routes
app = Flask(__name__)

# SUBSCRIBE
@app.route('/stomp/api/v1/subscribe', methods=['POST'])
def post_subscribe():
    j = request.get_json()
    if not j or not 'my_id' in j:
        abort(400)

    conn.subscribe(destination='/queue/'+j['my_id'], id=j['my_id'], ack='auto')
    return 'Successfully subscribed to '+j['my_id']

# ENQUEUE
@app.route('/stomp/api/v1/enqueue', methods=['POST'])
def post_enqueue():
    j = request.get_json()
    if not j or not 'ext_id' in j or not 'messageBody' in j:
        abort(400)

    b = json.dumps( j['messageBody'] )
    logger.info('Sending message to '+j['ext_id'])
    logger.debug('Sending message to '+j['ext_id']+':\n'+b)
    
    while conn.is_connected() == False:
        time.sleep(1)
    
    conn.send(body=b, destination='/queue/'+j['ext_id'])
    return 'Successfully enqueued message to '+j['ext_id']+': '+b

# DEQUEUE
@app.route('/stomp/api/v1/dequeue', methods=['POST'])
def post_dequeue():
    return "Test dequeue failed (this feature not yet implemented)"

if __name__ == '__main__':
    #app.run(port=5010, debug=False, use_reloader=False)
    serve(app, host='127.0.0.1', port=5010)
