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

from flask import Flask, request, jsonify, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import requests     
import json         

app = Flask(__name__)   
scheduler = BackgroundScheduler()
# Twilio credentials
TWILIO_ACCOUNT_SID = 'AC27c82b26078be0e551148c5fdf2d394a'
TWILIO_AUTH = '9b95d5d99e129525fc0a008b570ddb88'
TWILIO_PHONE_NUMBER = '+18505346392'  # Replace with your Twilio phone number      
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH)        
# Price thresholds for SOL  

SOL_PRICE_THRESHOLD = 20.0  # Example threshold for SOL price
SOL_PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd'        


def get_sol_price():
    try:
        response = requests.get(SOL_PRICE_URL)
        data = response.json()
        return data['solana']['usd']
    except Exception as e:
        print(f"Error fetching SOL price: {e}")
        return None     

def check_sol_price():      
    sol_price = get_sol_price()
    if sol_price is not None:
        if sol_price < SOL_PRICE_THRESHOLD:
            send_sms_alert(sol_price)

def send_sms_alert(price):
    message = f"Alert: SOL price has dropped below ${SOL_PRICE_THRESHOLD}. Current price: ${price}"
    client.messages.create(
        body=message,
        from_=TWILIO_PHONE_NUMBER,
        to='+919167788888'  # Replace with your phone number
    )
    print(f"SMS sent: {message}")

def meeting_reminder_job():
    from datetime import datetime, timedelta
    now = datetime.now()
    for meeting in meetings:
        if not meeting['reminded']:
            meeting_time = meeting['datetime']
            if 0 <= (meeting_time - now).total_seconds() <= 300:  # 5 minutes = 300 seconds
                msg = f"Reminder: Meeting with {meeting['with']} at {meeting['time']} on {meeting['date']}. Agenda: {meeting['agenda']} (in 5 minutes)"
                client.messages.create(
                    body=msg,
                    from_=TWILIO_PHONE_NUMBER,
                    to='+918209544626'  # Replace with your phone
                )
                print(f"Meeting reminder SMS sent: {msg}")
                meeting['reminded'] = True

scheduler.add_job(check_sol_price, 'interval', minutes=1)  # Check every minute
scheduler.add_job(meeting_reminder_job, 'interval', minutes=1)  # Check for meeting reminders every minute
scheduler.start()


# In-memory meeting store for reminders
meetings = []

# In-memory Solana price alert limits
solana_alert = {'lower': None, 'upper': None, 'notified': False}

@app.route('/solana_limit', methods=['GET', 'POST'])
def solana_limit():
    message = None
    if request.method == 'POST':
        try:
            lower = float(request.form.get('lower'))
            upper = float(request.form.get('upper'))
            solana_alert['lower'] = lower
            solana_alert['upper'] = upper
            solana_alert['notified'] = False
            message = f"Limits set: Lower = {lower}, Upper = {upper}"
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
                <form method="post" class="mb-3">
                    <div class="mb-2">
                        <label>Lower Limit ($)</label>
                        <input type="number" step="0.01" name="lower" class="form-control" value="{{ lower }}" required>
                    </div>
                    <div class="mb-2">
                        <label>Upper Limit ($)</label>
                        <input type="number" step="0.01" name="upper" class="form-control" value="{{ upper }}" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Set Alert Limits</button>
                </form>
                {% if message %}<div class="alert alert-info">{{ message }}</div>{% endif %}
                <a href="/">Back to Home</a>
            </div>
        </body>
        </html>
    ''', lower=solana_alert['lower'] or '', upper=solana_alert['upper'] or '', message=message)

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

    # Store meeting in memory for reminders
    try:
        meeting_dt = datetime.strptime(f"{date} {time_}", "%d-%m-%Y %H:%M")
        meetings.append({
            'with': with_person,
            'date': date,
            'time': time_,
            'agenda': agenda,
            'datetime': meeting_dt,
            'reminded': False
        })
    except Exception as e:
        return jsonify({"error": f"Invalid date/time format: {e}"}), 400

    print(f"Meeting scheduled with {with_person} on {date} at {time_}. Agenda: {agenda}")

    # Send SMS on meeting creation
    message = f"Meeting scheduled with {with_person} on {date} at {time_}. Agenda: {agenda}"
    client.messages.create(
        body=message,
        from_=TWILIO_PHONE_NUMBER,
        to='+918209544626'  # Replace with your phone 
    )
    print(f"SMS sent: {message}")

    return jsonify({"message": "Meeting added successfully"}), 200

@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    from datetime import datetime
    message = None
    if request.method == 'POST':
        with_person = request.form.get('with')
        date = request.form.get('date')
        time_ = request.form.get('time')
        agenda = request.form.get('agenda')

        if not all([with_person, date, time_, agenda]):
            message = "❌ Missing required fields."
        else:
            try:
                meeting_dt = datetime.strptime(f"{date} {time_}", "%d-%m-%Y %H:%M")
                meetings.append({
                    'with': with_person,
                    'date': date,
                    'time': time_,
                    'agenda': agenda,
                    'datetime': meeting_dt,
                    'reminded': False
                })
            except Exception as e:
                message = f"Invalid date/time format: {e}"
            msg = f"Meeting scheduled with {with_person} on {date} at {time_}. Agenda: {agenda}"
            client.messages.create(
                body=msg,
                from_=TWILIO_PHONE_NUMBER,
                to='+918209544626'  # Replace with your phone
            )
            message = "✅ Meeting scheduled and WhatsApp/SMS sent!"

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>AI Meeting Scheduler</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {
                background: #f7f7f8;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .card {
                border-radius: 1rem;
                box-shadow: 0 4px 32px rgba(0,0,0,0.08);
                padding: 2rem;
                max-width: 400px;
                width: 100%;
            }
            .form-label {
                font-weight: 500;
            }
            .btn-primary {
                background: #10a37f;
                border: none;
            }
            .btn-primary:hover {
                background: #0e8c6c;
            }
            .mic-btn {
                background: #fff;
                border: 2px solid #10a37f;
                color: #10a37f;
                border-radius: 50%;
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 1rem auto;
                cursor: pointer;
                transition: background 0.2s;
            }
            .mic-btn.active {
                background: #10a37f;
                color: #fff;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h2 class="mb-4 text-center" style="font-weight:700;">AI Meeting Scheduler</h2>
            <button type="button" class="mic-btn" id="micBtn" title="Speak your meeting details">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" class="bi bi-mic" viewBox="0 0 16 16">
                  <path d="M8 12a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v4a3 3 0 0 0 3 3z"/>
                  <path d="M5 10.5a.5.5 0 0 1 .5.5v1a2.5 2.5 0 0 0 5 0v-1a.5.5 0 0 1 1 0v1a3.5 3.5 0 0 1-7 0v-1a.5.5 0 0 1 .5-.5z"/>
                </svg>
            </button>
            <div class="text-center mb-3" id="voiceStatus" style="font-size:0.95rem;color:#888;"></div>
            {% if message %}
                <div class="alert alert-info">{{ message }}</div>
            {% endif %}
            <form method="post" id="meetingForm">
                <div class="mb-3">
                    <label class="form-label">With</label>
                    <input type="text" class="form-control" name="with" id="withInput" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">Date</label>
                    <input type="text" class="form-control" name="date" id="dateInput" placeholder="DD-MM-YYYY" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">Time</label>
                    <input type="text" class="form-control" name="time" id="timeInput" placeholder="HH:MM" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">Agenda</label>
                    <input type="text" class="form-control" name="agenda" id="agendaInput" required>
                </div>
                <button type="submit" class="btn btn-primary w-100">Schedule Meeting</button>
            </form>
        </div>
        <script>
        // Voice recognition logic (fills all fields from transcript)
        const micBtn = document.getElementById('micBtn');
        const voiceStatus = document.getElementById('voiceStatus');
        const withInput = document.getElementById('withInput');
        const dateInput = document.getElementById('dateInput');
        const timeInput = document.getElementById('timeInput');
        const agendaInput = document.getElementById('agendaInput');

        let recognition;
        if ('webkitSpeechRecognition' in window) {
            recognition = new webkitSpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-US';

            micBtn.onclick = function() {
                recognition.start();
                micBtn.classList.add('active');
                voiceStatus.textContent = "Listening... Please say: 'Meeting with [name] on [date] at [time] about [agenda]'";
            };

            recognition.onresult = function(event) {
                micBtn.classList.remove('active');
                voiceStatus.textContent = "";
                const transcript = event.results[0][0].transcript;

                // Basic parsing logic
                // Example: "Meeting with Akshat on 30-07-2025 at 14:00 about project update"
                let withMatch = transcript.match(/with ([\w\s]+)/i);
                let dateMatch = transcript.match(/on ([\d\-\/\w\s]+)/i);
                let timeMatch = transcript.match(/at ([\d:apm\s]+)/i);
                let agendaMatch = transcript.match(/about (.+)$/i);

                if (withMatch) withInput.value = withMatch[1].trim();
                if (dateMatch) dateInput.value = dateMatch[1].trim();
                if (timeMatch) timeInput.value = timeMatch[1].trim();
                if (agendaMatch) agendaInput.value = agendaMatch[1].trim();

                voiceStatus.textContent = "Fields filled from voice! Please review and submit.";
            };

            recognition.onerror = function(event) {
                micBtn.classList.remove('active');
                voiceStatus.textContent = "Voice recognition error. Try again.";
            };
        } else {
            micBtn.disabled = true;
            voiceStatus.textContent = "Voice recognition not supported in this browser.";
        }
        </script>
    </body>
    </html>
    """, message=message)

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
        </div>
    </body>
    </html>
    ''')

@app.route('/meetings')
def meetings_list():
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
        </style>
    </head>
    <body>
        <div class="container">
            <h2 class="mb-4 text-center" style="font-weight:700;">Scheduled Meetings & Events</h2>
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
    ''', meetings=meetings)
    return "✅ AI Agent Running"

if __name__ == '__main__':
    app.run(debug=True)


