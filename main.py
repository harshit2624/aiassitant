 # To run the app, use the command: python main.py
# Ensure you have Flask, APScheduler, Twilio, and requests installed.
# You can install them using pip:
# pip install Flask APScheduler twilio requests
# Make sure to replace the Twilio credentials with your own.
# The app will run on http://localhost:5000 and you can add meetings via POST       
# requests to /add endpoint with JSON body:
# Example:
# curl -X POST http://127.0.0.1:5000/add -H "Content-Type: application/json" -d '{"with":"Sam", "date":"30-07-2025", "time":"14:00", "agenda":"Follow-up on AI project"}'
# The SOL Tracker will send SMS alerts based on the defined price thresholds.

import os                                   
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request, jsonify, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import requests     
import json         
from pymongo import MongoClient
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import ssl

# MongoDB Atlas connection
MONGO_URI = "mongodb+srv://harshitvj24:Harshit%40321@cluster0.2rw2irv.mongodb.net/?retryWrites=false&w=majority&tls=true&tlsAllowInvalidCertificates=true&appName=Cluster0"
from pymongo.errors import ServerSelectionTimeoutError

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, tls=True, tlsAllowInvalidCertificates=True)
    mongo_client.server_info()  # Force connection on a request as a test
    print("MongoDB connection successful")
except ServerSelectionTimeoutError as e:
    print(f"MongoDB connection failed: {e}")
    # Fallback to local MongoDB for development/testing
    mongo_client = MongoClient("mongodb://localhost:27017/")
    print("Connected to local MongoDB fallback")
mongo_db = mongo_client['meeting_db']
meetings_collection = mongo_db['meetings']
solana_collection = mongo_db['solana_alert']         

app = Flask(__name__)   
scheduler = BackgroundScheduler()
# Twilio credentials
TWILIO_ACCOUNT_SID = 'AC27c82b26078be0e551148c5fdf2d394a'
TWILIO_AUTH = '503b9f7cb975fc087de53145b85fbe68'
TWILIO_PHONE_NUMBER = '+18505346392'  # Replace with your Twilio phone number      
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH)        

# SMS provider selection: 'twilio', 'textbelt', or 'smtp'
SMS_PROVIDER = os.getenv('SMS_PROVIDER', 'twilio')

# Textbelt API key (use 'textbelt' for free tier)
TEXTBELT_API_KEY = os.getenv('TEXTBELT_API_KEY', 'textbelt')

# SMTP configuration for SMTP to SMS
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL')

# Carrier SMS gateway domain mapping (including Airtel)
CARRIER_GATEWAYS = {
    'att': 'txt.att.net',
    'verizon': 'vtext.com',
    'tmobile': 'tmomail.net',
    'airtel': 'airtelmail.in',  # Corrected Airtel India SMS gateway domain
    # Add more carriers as needed
}

def send_email(to_email, subject, body):
    """
    Send an email via SMTP.
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, to_email, msg.as_string())
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# Price thresholds for SOL  

SOL_PRICE_THRESHOLD = 20.0  # Example threshold for SOL price
SOL_PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd'        


def get_asset_price(asset_symbol):
    """
    Fetch current price for given asset symbol.
    For cryptos, use Binance API with symbol + 'USDT'.
    For Indian stocks, return None (or implement API if available).
    """
    try:
        # Check if asset is crypto (simple check: if symbol is uppercase and length <=5)
        if asset_symbol.isalpha() and asset_symbol.isupper() and len(asset_symbol) <= 5:
            # For cryptos, use Binance API
            symbol = asset_symbol + 'USDT'
            response = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}')
            data = response.json()
            price = float(data['price'])
            return price
        else:
            # For Indian stocks, no API implemented, return None or mock
            return None
    except Exception as e:
        print(f"Error fetching price for {asset_symbol}: {e}")
        return None

def check_sol_price():      
    sol_price = get_sol_price()
    if sol_price is not None:
        if sol_price < SOL_PRICE_THRESHOLD:
            send_sms_alert(sol_price)

def send_sms_alert(price):
    message = f"Alert: SOL price has dropped below ${SOL_PRICE_THRESHOLD}. Current price: ${price}"
    if SMS_PROVIDER == 'twilio':
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to='+918209544626'  # Replace with your phone number
        )
        print(f"Twilio SMS sent: {message}")
    elif SMS_PROVIDER == 'textbelt':
        import requests
        payload = {
            'phone': '+918209544626',  # Replace with your phone number
            'message': message,
            'key': TEXTBELT_API_KEY
        }
        response = requests.post('https://textbelt.com/text', data=payload)
        result = response.json()
        if result.get('success'):
            print(f"Textbelt SMS sent: {message}")
        else:
            print(f"Failed to send Textbelt SMS: {result.get('error')}")
    elif SMS_PROVIDER == 'smtp':
        # Example: specify carrier here or make it configurable
        carrier = 'att'
        phone_number = '918209544626'  # Replace with your phone number without '+' and country code if needed
        send_sms_via_smtp(phone_number, message, carrier)

def meeting_reminder_job():
    from datetime import datetime, timedelta
    now = datetime.now()
    for meeting in meetings_collection.find({'reminded': False}):
        meeting_time = datetime.strptime(meeting['datetime'], "%Y-%m-%d %H:%M")
        if 0 <= (meeting_time - now).total_seconds() <= 300:  # 5 minutes = 300 seconds
            msg = f"Reminder: Meeting with {meeting['with']} at {meeting['time']} on {meeting['date']}. Agenda: {meeting['agenda']} (in 5 minutes)"
            if SMS_PROVIDER == 'twilio':
                client.messages.create(
                    body=msg,
                    from_=TWILIO_PHONE_NUMBER,
                    to='+918209544626'  # Replace with your phone
                )
                print(f"Twilio meeting reminder SMS sent: {msg}")
            elif SMS_PROVIDER == 'textbelt':
                import requests
                payload = {
                    'phone': '+918209544626',  # Replace with your phone number
                    'message': msg,
                    'key': TEXTBELT_API_KEY
                }
                response = requests.post('https://textbelt.com/text', data=payload)
                result = response.json()
                if result.get('success'):
                    print(f"Textbelt meeting reminder SMS sent: {msg}")
                else:
                    print(f"Failed to send Textbelt meeting reminder SMS: {result.get('error')}")
            elif SMS_PROVIDER == 'smtp':
                carrier = 'att'
                phone_number = '918209544626'  # Replace with your phone number without '+' and country code if needed
                send_sms_via_smtp(phone_number, msg, carrier)
            meetings_collection.update_one({'_id': meeting['_id']}, {'$set': {'reminded': True}})

scheduler.add_job(check_sol_price, 'interval', minutes=1)  # Check every minute
scheduler.add_job(meeting_reminder_job, 'interval', minutes=1)  # Check for meeting reminders every minute
scheduler.start()

@app.route('/send_email', methods=['POST'])
def send_email_route():
    data = request.get_json()
    to_email = data.get('to_email')
    subject = data.get('subject', 'No Subject')
    body = data.get('body', '')

    if not to_email:
        return jsonify({'error': 'to_email is required'}), 400

    success = send_email(to_email, subject, body)
    if success:
        return jsonify({'message': f'Email sent to {to_email}'}), 200
    else:
        return jsonify({'error': 'Failed to send email'}), 500

# Uncomment the following line to run the test when starting the app
# test_smtp_sms()


# Remove in-memory meeting store and solana_alert
solana_alert = {'lower': None, 'upper': None, 'notified': False}

@app.route('/solana_limit', methods=['GET', 'POST'])
def solana_limit():
    message = None
    # Load current limits from DB
    solana_doc = solana_collection.find_one({})
    lower = solana_doc['lower'] if solana_doc and 'lower' in solana_doc else ''
    upper = solana_doc['upper'] if solana_doc and 'upper' in solana_doc else ''
    current_price = get_sol_price()
    if request.method == 'POST':
        try:
            lower = float(request.form.get('lower'))
            upper = float(request.form.get('upper'))
            # solana_collection.delete_many({})  # Remove deletion to keep multiple alerts
            solana_collection.insert_one({'lower': lower, 'upper': upper, 'notified': False})
            message = f"Alert added: Lower = {lower}, Upper = {upper}"
        except Exception as e:
            message = f"Invalid input: {e}"
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <title>Solana Price Alert</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background: #f7f7f8; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                .solana-card { border-radius: 1rem; box-shadow: 0 4px 32px rgba(0,0,0,0.08); padding: 2.5rem 2rem; max-width: 420px; width: 100%; background: #fff; margin: 1rem; text-align: center; }
            </style>
        </head>
        <body>
            <div class="solana-card">
                <h2 class="mb-4" style="font-weight:700;">Solana Price Alert</h2>
                <h4>Current Solana Price: ${{ current_price if current_price is not none else 'Unavailable' }}</h4>
                <form method="post" class="mb-3">
                    <div class="mb-2">
                        <label>Lower Limit ($)</label>
                        <input type="number" step="0.01" name="lower" class="form-control" required>
                    </div>
                    <div class="mb-2">
                        <label>Upper Limit ($)</label>
                        <input type="number" step="0.01" name="upper" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Add Alert</button>
                </form>
                {% if message %}<div class="alert alert-info">{{ message }}</div>{% endif %}
                <a href="/">Back to Home</a>
            </div>
        </body>
        </html>
    ''', message=message, current_price=current_price)

# Background job to check Solana price and send alert
import threading
solana_lock = threading.Lock()
def solana_price_alert():
    price = get_sol_price()
    with solana_lock:
        lower = solana_alert['lower']
        upper = solana_alert['upper']
        notified = solana_alert['notified']
        if price is not None and lower is not None and upper is not None:
            if (price < lower or price > upper) and not notified:
                msg = f"ALERT: Solana price ${price} is outside your set range (${lower} - ${upper})!"
                client.messages.create(
                    body=msg,
                    from_=TWILIO_PHONE_NUMBER,
                    to='+918209544626'
                )
                print(f"Solana alert SMS sent: {msg}")
                solana_alert['notified'] = True
            elif lower <= price <= upper:
                solana_alert['notified'] = False

scheduler.add_job(solana_price_alert, 'interval', minutes=1)

@app.route('/add', methods=['POST'])
def add_meeting():
    from datetime import datetime
    data = request.get_json()
    with_person = data.get('with')
    date = data.get('date')
    time_ = data.get('time')
    agenda = data.get('agenda')

    if not all([with_person, date, time_, agenda]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        meeting_dt = datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M")
        # Insert meeting into MongoDB
        result = meetings_collection.insert_one({
            'with': with_person,
            'date': date,
            'time': time_,
            'agenda': agenda,
            'datetime': meeting_dt.strftime("%Y-%m-%d %H:%M"),
            'reminded': False
        })
        print(f"Inserted meeting with id: {result.inserted_id}")
    except Exception as e:
        print(f"Error inserting meeting: {e}")
        return jsonify({"error": f"Invalid date/time format: {e}"}), 400

    print(f"Meeting scheduled with {with_person} on {date} at {time_}. Agenda: {agenda}")

    # Send SMS on meeting creation
    message = f"Meeting scheduled with {with_person} on {date} at {time_}. Agenda: {agenda}"
    if SMS_PROVIDER == 'twilio':
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to='+918209544626'  # Replace with your phone 
        )
        print(f"Twilio SMS sent: {message}")
    elif SMS_PROVIDER == 'textbelt':
        import requests
        payload = {
            'phone': '+918209544626',  # Replace with your phone number
            'message': message,
            'key': TEXTBELT_API_KEY
        }
        response = requests.post('https://textbelt.com/text', data=payload)
        result = response.json()
        if result.get('success'):
            print(f"Textbelt SMS sent: {message}")
        else:
            print(f"Failed to send Textbelt SMS: {result.get('error')}")

    return jsonify({"message": "Meeting added successfully"}), 200


@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    if request.method == 'POST':
        data = request.form
        with_person = data.get('with')
        date = data.get('date')
        time_ = data.get('time')
        agenda = data.get('agenda')

        if not all([with_person, date, time_, agenda]):
            return render_template_string(schedule_form_template, error="All fields are required.", form=data)

        import datetime
        try:
            meeting_dt = datetime.datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M")
        except Exception as e:
            return render_template_string(schedule_form_template, error=f"Invalid date/time format: {e}", form=data)

        # Insert meeting into MongoDB
        try:
            meetings_collection.insert_one({
                'with': with_person,
                'date': date,
                'time': time_,
                'agenda': agenda,
                'datetime': meeting_dt.strftime("%Y-%m-%d %H:%M"),
                'reminded': False
            })
        except Exception as e:
            return render_template_string(schedule_form_template, error=f"Database error: {e}", form=data)

        # Send SMS on meeting creation
        message = f"Meeting scheduled with {with_person} on {date} at {time_}. Agenda: {agenda}"
        if SMS_PROVIDER == 'twilio':
            client.messages.create(
                body=message,
                from_=TWILIO_PHONE_NUMBER,
                to='+918209544626'  # Replace with your phone 
            )
            print(f"Twilio SMS sent: {message}")
        elif SMS_PROVIDER == 'textbelt':
            import requests
            payload = {
                'phone': '+918209544626',  # Replace with your phone number
                'message': message,
                'key': TEXTBELT_API_KEY
            }
            response = requests.post('https://textbelt.com/text', data=payload)
            result = response.json()
            if result.get('success'):
                print(f"Textbelt SMS sent: {message}")
            else:
                print(f"Failed to send Textbelt SMS: {result.get('error')}")
        elif SMS_PROVIDER == 'smtp':
            carrier = 'att'
            phone_number = '918209544626'  # Replace with your phone number without '+' and country code if needed
            send_sms_via_smtp(phone_number, message, carrier)

        return render_template_string(schedule_form_template, success="Meeting scheduled successfully!")

    else:
        return render_template_string(schedule_form_template)

schedule_form_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Schedule Meeting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f7f7f8; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .schedule-card {
            border-radius: 1rem;
            box-shadow: 0 4px 32px rgba(0,0,0,0.08);
            padding: 2.5rem 2rem;
            max-width: 420px;
            width: 100%;
            background: #fff;
            margin: 1rem;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="schedule-card">
        <h2 class="mb-4" style="font-weight:700;">Schedule Meeting</h2>
        {% if error %}
            <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        {% if success %}
            <div class="alert alert-success">{{ success }}</div>
        {% endif %}
        <form method="post" class="mb-3">
            <div class="mb-2">
                <label>With</label>
                <input type="text" name="with" class="form-control" value="{{ form.with if form else '' }}" required>
            </div>
            <div class="mb-2">
                <label>Date</label>
                <input type="date" name="date" class="form-control" value="{{ form.date if form else '' }}" required>
            </div>
            <div class="mb-2">
                <label>Time</label>
                <input type="time" name="time" class="form-control" value="{{ form.time if form else '' }}" required>
            </div>
            <div class="mb-2">
                <label>Agenda</label>
                <textarea name="agenda" class="form-control" rows="3" required>{{ form.agenda if form else '' }}</textarea>
            </div>
            <button type="submit" class="btn btn-primary w-100">Schedule</button>
        </form>
        <a href="/" class="btn btn-secondary w-100">Back to Home</a>
    </div>
</body>
</html>
'''

schedule_form_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Schedule Meeting</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f7f7f8; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .schedule-card {
            border-radius: 1rem;
            box-shadow: 0 4px 32px rgba(0,0,0,0.08);
            padding: 2.5rem 2rem;
            max-width: 420px;
            width: 100%;
            background: #fff;
            margin: 1rem;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="schedule-card">
        <h2 class="mb-4" style="font-weight:700;">Schedule Meeting</h2>
        {% if error %}
            <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        {% if success %}
            <div class="alert alert-success">{{ success }}</div>
        {% endif %}
        <form method="post" class="mb-3">
            <div class="mb-2">
                <label>With</label>
                <input type="text" name="with" class="form-control" value="{{ form.with if form else '' }}" required>
            </div>
            <div class="mb-2">
                <label>Date</label>
                <input type="date" name="date" class="form-control" value="{{ form.date if form else '' }}" required>
            </div>
            <div class="mb-2">
                <label>Time</label>
                <input type="time" name="time" class="form-control" value="{{ form.time if form else '' }}" required>
            </div>
            <div class="mb-2">
                <label>Agenda</label>
                <textarea name="agenda" class="form-control" rows="3" required>{{ form.agenda if form else '' }}</textarea>
            </div>
            <button type="submit" class="btn btn-primary w-100">Schedule</button>
        </form>
        <a href="/" class="btn btn-secondary w-100">Back to Home</a>
    </div>
</body>
</html>
'''


@app.route('/meetings')
def meetings_list():
    meetings = list(meetings_collection.find())
    solana_triggers = list(solana_collection.find())
    crypto_stock_limits = list(crypto_stock_collection.find())
    current_price = None
    try:
        response = requests.get(SOL_PRICE_URL)
        data = response.json()
        current_price = data['solana']['usd']
    except Exception as e:
        print(f"Error fetching SOL price: {e}")

    # Fetch current prices for crypto and stock limits
    for limit in crypto_stock_limits:
        limit['current_price'] = get_asset_price(limit['asset'])

    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Scheduled Meetings & Events</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: #f7f7f8; min-height: 100vh; }
            .container { max-width: 700px; margin: 2rem auto; }
            .meeting-card { background: #fff; border-radius: 1rem; box-shadow: 0 4px 32px rgba(0,0,0,0.08); padding: 1.5rem 2rem; margin-bottom: 1.5rem; }
            .solana-limits { border-radius: 0.7rem; padding: 1rem 1.5rem; margin-bottom: 2rem; border: 1px solid #10a37f22; }
            .alert-triggered { background-color: #f8d7da; border-color: #f5c2c7; }
            .crypto-stock-limits { border-radius: 0.7rem; padding: 1rem 1.5rem; margin-bottom: 2rem; border: 1px solid #1070a322; }
            .alert-crypto-triggered { background-color: #f8f0da; border-color: #f5e2c7; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2 class="mb-4 text-center" style="font-weight:700;">Scheduled Meetings & Events</h2>
            <div class="solana-limits mb-4">
                <b>Solana Price Alerts:</b><br>
                {% if solana_triggers %}
                    <ul class="list-group mb-3">
                    {% for t in solana_triggers %}
                        {% set triggered = (current_price is not none and t['lower'] is not none and t['upper'] is not none and (current_price < t['lower'] or current_price > t['upper'])) %}
                        <li class="list-group-item {% if triggered %}alert-triggered{% endif %}">
                            Alert Range: <b>${{ t['lower'] }}</b> - <b>${{ t['upper'] }}</b>
                            {% if triggered %}
                                <span class="badge bg-danger">Triggered</span>
                            {% endif %}
                        </li>
                    {% endfor %}
                    </ul>
                {% else %}
                    <div class="alert alert-info">No active Solana alerts.</div>
                {% endif %}
            </div>
            <div class="crypto-stock-limits mb-4">
                <b>Crypto & Indian Stocks Price Alerts:</b><br>
                {% if crypto_stock_limits %}
                    <ul class="list-group mb-3">
                    {% for limit in crypto_stock_limits %}
                        {% set triggered = (limit.current_price is not none and limit.lower is not none and limit.upper is not none and (limit.current_price < limit.lower or limit.current_price > limit.upper)) %}
                        <li class="list-group-item {% if triggered %}alert-crypto-triggered{% endif %}">
                            Asset: <b>{{ limit.asset }}</b> | Current Price: <b>{{ limit.current_price if limit.current_price is not none else 'Unavailable' }}</b> | Alert Range: <b>${{ limit.lower }}</b> - <b>${{ limit.upper }}</b>
                            {% if triggered %}
                                <span class="badge bg-warning text-dark">Triggered</span>
                            {% endif %}
                        </li>
                    {% endfor %}
                    </ul>
                {% else %}
                    <div class="alert alert-info">No active Crypto/Stock alerts.</div>
                {% endif %}
            </div>
            {% if meetings %}
                {% for m in meetings %}
                <div class="meeting-card">
                    <div><b>With:</b> {{ m['with'] }}</div>
                    <div><b>Date:</b> {{ m['date'] }}</div>
                    <div><b>Time:</b> {{ m['time'] }}</div>
                    <div><b>Agenda:</b> {{ m['agenda'] }}</div>
                </div>
                {% endfor %}
            {% else %}
                <div class="alert alert-info text-center">No meetings/events scheduled.</div>
            {% endif %}
            <div class="text-center mt-4"><a href="/" class="btn btn-secondary">Back to Home</a></div>
        </div>
    </body>
    </html>
    ''', meetings=meetings, solana_triggers=solana_triggers, current_price=current_price, crypto_stock_limits=crypto_stock_limits)

crypto_stock_collection = mongo_db['crypto_stock_limits']

@app.route('/crypto_stock_limits', methods=['GET', 'POST'])
def crypto_stock_limits():
    message = None
    # Predefined list of popular cryptos and Indian stocks symbols for autocomplete
    asset_options = [
        'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOT', 'DOGE', 'LTC', 'BCH', 'LINK',
        'INFY', 'TCS', 'HDFCBANK', 'RELIANCE', 'ICICIBANK', 'HINDUNILVR', 'SBIN', 'KOTAKBANK', 'LT', 'AXISBANK'
    ]
    # Load current limits from DB
    limits = list(crypto_stock_collection.find())
    if request.method == 'POST':
        try:
            asset = request.form.get('asset')
            lower = float(request.form.get('lower'))
            upper = float(request.form.get('upper'))
            if not asset:
                message = "Asset name is required."
            else:
                # Check if asset already exists
                existing = crypto_stock_collection.find_one({'asset': asset})
                if existing:
                    crypto_stock_collection.update_one({'asset': asset}, {'$set': {'lower': lower, 'upper': upper, 'notified': False}})
                    message = f"Updated alert for {asset}: Lower = {lower}, Upper = {upper}"
                else:
                    crypto_stock_collection.insert_one({'asset': asset, 'lower': lower, 'upper': upper, 'notified': False})
                    message = f"Added alert for {asset}: Lower = {lower}, Upper = {upper}"
                limits = list(crypto_stock_collection.find())
        except Exception as e:
            message = f"Invalid input: {e}"

    # Fetch current prices for each limit
    for limit in limits:
        limit['current_price'] = get_asset_price(limit['asset'])

    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Crypto & Indian Stocks Limits</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: #f7f7f8; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding: 2rem; }
            .limits-card { border-radius: 1rem; box-shadow: 0 4px 32px rgba(0,0,0,0.08); padding: 2rem; max-width: 600px; width: 100%; background: #fff; margin-bottom: 2rem; }
            table { width: 100%; }
            th, td { padding: 0.75rem; text-align: left; }
            th { background-color: #10a37f22; }
            .alert-triggered { background-color: #f8d7da; }
        </style>
    </head>
    <body>
        <div class="limits-card">
            <h2 class="mb-4" style="font-weight:700;">Set Limits for Cryptos & Indian Stocks</h2>
            <form method="post" class="mb-4">
                <div class="mb-3">
                    <label>Asset Symbol (e.g., BTC, INFY)</label>
                    <input list="assetOptions" name="asset" class="form-control" required>
                    <datalist id="assetOptions">
                        {% for option in asset_options %}
                        <option value="{{ option }}">
                        {% endfor %}
                    </datalist>
                </div>
                <div class="mb-3">
                    <label>Lower Limit</label>
                    <input type="number" step="0.01" name="lower" class="form-control" required>
                </div>
                <div class="mb-3">
                    <label>Upper Limit</label>
                    <input type="number" step="0.01" name="upper" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-primary w-100">Add / Update Alert</button>
            </form>
            {% if message %}
                <div class="alert alert-info">{{ message }}</div>
            {% endif %}
            {% if limits %}
                <table class="table table-bordered">
                    <thead>
                        <tr>
                            <th>Asset</th>
                            <th>Lower Limit</th>
                            <th>Upper Limit</th>
                            <th>Current Price</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for limit in limits %}
                        <tr class="{% if limit.notified %}alert-triggered{% endif %}">
                            <td>{{ limit.asset }}</td>
                            <td>{{ limit.lower }}</td>
                            <td>{{ limit.upper }}</td>
                            <td>{{ limit.current_price if limit.current_price is not none else 'Unavailable' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <p>No alerts set.</p>
            {% endif %}
            <a href="/" class="btn btn-secondary mt-3">Back to Home</a>
        </div>
    </body>
    </html>
    ''', message=message, limits=limits, asset_options=asset_options)

@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>AI Meeting Agent</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: #f7f7f8; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .icon-card {
                border-radius: 1rem;
                box-shadow: 0 4px 32px rgba(0,0,0,0.08);
                padding: 2.5rem 2rem;
                max-width: 420px;
                width: 100%;
                background: #fff;
                margin: 1rem;
                text-align: center;
                transition: box-shadow 0.2s;
            }
            .icon-card:hover {
                box-shadow: 0 8px 40px rgba(16,163,127,0.15);
            }
            .icon-btn {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-decoration: none;
                color: #222;
                font-size: 1.3rem;
                font-weight: 600;
            }
            .icon-btn svg {
                width: 72px;
                height: 72px;
                margin-bottom: 1rem;
                color: #10a37f;
            }
            @media (max-width: 900px) {
                .icon-card { max-width: 95vw; }
            }
        </style>
    </head>
    <body>
        <div class="d-flex flex-wrap justify-content-center align-items-center w-100" style="gap:2rem;">
            <a href="/schedule" class="icon-card icon-btn">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="13" rx="2" stroke="#10a37f" stroke-width="2"/><path d="M16 3v4M8 3v4M3 11h18" stroke="#10a37f" stroke-width="2"/></svg>
                Schedule Meeting
            </a>
            <a href="/solana_limit" class="icon-card icon-btn">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="13" rx="2" stroke="#10a37f" stroke-width="2"/><path d="M8 15h8M8 11h8" stroke="#10a37f" stroke-width="2"/><circle cx="12" cy="12" r="10" stroke="#10a37f" stroke-width="2"/></svg>
                Solana Price Tracker
            </a>
            <a href="/meetings" class="icon-card icon-btn">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2" stroke="#10a37f" stroke-width="2"/><path d="M8 10h8M8 14h8" stroke="#10a37f" stroke-width="2"/></svg>
                View Scheduled Meetings & Events
            </a>
            <a href="/crypto_stock_limits" class="icon-card icon-btn">
                <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="#10a37f" stroke-width="2"/><path d="M8 12h8M12 8v8" stroke="#10a37f" stroke-width="2"/></svg>
                Crypto & Indian Stocks Limits
            </a>
        </div>
    </body>
    </html>
    ''')

if __name__ == '__main__':
    app.run(debug=True)
