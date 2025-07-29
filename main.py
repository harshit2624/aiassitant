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
TWILIO_AUTH = '4320ce4c54483119eb5baa53b78a2508'
TWILIO_PHONE_NUMBER = '++18505346392'  # Replace with your Twilio phone number      
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

scheduler.add_job(check_sol_price, 'interval', minutes=1)  # Check every minute
scheduler.start()


@app.route('/add', methods=['POST'])
def add_meeting():
    data = request.get_json()
    with_person = data.get('with')
    date = data.get('date')
    time_ = data.get('time')
    agenda = data.get('agenda')

    if not all([with_person, date, time_, agenda]):
        return jsonify({"error": "Missing required fields"}), 400

    # For demonstration, just print the meeting details
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
    message = None
    if request.method == 'POST':
        with_person = request.form.get('with')
        date = request.form.get('date')
        time_ = request.form.get('time')
        agenda = request.form.get('agenda')

        if not all([with_person, date, time_, agenda]):
            message = "❌ Missing required fields."
        else:
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
    return "✅ AI Agent Running"

if __name__ == '__main__':
    app.run(debug=True)
git init
git add .





