from flask import Flask, render_template, request, redirect, session
import boto3
import uuid
import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

app = Flask(__name__)
app.secret_key = "travelgo_secret"

# ---------------- AWS CONNECTION ----------------
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
sns = boto3.client('sns', region_name='ap-south-1')

users_table = dynamodb.Table('travel-Users')
bookings_table = dynamodb.Table('Bookings')

# Replace with your actual SNS ARN
SNS_TOPIC_ARN = "arn:aws:sns:ap-south-1:873461661958:TravelGoNotifications"

# ---------------- STATIC DATA ----------------
bus_data = [
    {"id": "B1", "name": "Super Luxury Bus", "source": "Hyderabad", "dest": "Bangalore", "price": 800},
    {"id": "B2", "name": "Express Bus", "source": "Chennai", "dest": "Hyderabad", "price": 700}
]

train_data = [
    {"id": "T1", "name": "Rajdhani Express", "source": "Hyderabad", "dest": "Delhi", "price": 1500},
    {"id": "T2", "name": "Shatabdi Express", "source": "Chennai", "dest": "Bangalore", "price": 900}
]

flight_data = [
    {"id": "F1", "name": "Indigo 6E203", "source": "Hyderabad", "dest": "Dubai", "price": 8500},
    {"id": "F2", "name": "Air India AI102", "source": "Delhi", "dest": "Singapore", "price": 9500}
]

hotel_data = [
    {"id": "H1", "name": "Grand Palace", "city": "Chennai", "type": "Luxury", "price": 4000},
    {"id": "H2", "name": "Budget Inn", "city": "Hyderabad", "type": "Budget", "price": 1500}
]

# Helper to find details by ID
def get_transport_details(t_id):
    all_transport = bus_data + train_data + flight_data
    for t in all_transport:
        if t['id'] == t_id:
            return f"{t['name']} | {t['source']} - {t['dest']}"
    for h in hotel_data:
        if h['id'] == t_id:
            return f"{h['name']} | {h['city']} ({h['type']})"
    return "Transport Details"

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users_table.put_item(
            Item={
                'email': request.form['email'],
                'name': request.form['name'],
                'password': request.form['password'],
                'logins': 0
            }
        )
        return redirect('/login')
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            response = users_table.get_item(Key={'email': request.form['email']})
            user = response.get('Item')
            if user and user['password'] == request.form['password']:
                session['user'] = user['email']
                session['name'] = user['name']
                return redirect('/dashboard')
            return render_template("login.html", error="Invalid Credentials")
        except Exception as e:
            return render_template("login.html", error=str(e))
    return render_template("login.html")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    
    # Scanning is not efficient for production but works for small demos. 
    # Ideally use Query with a Global Secondary Index (GSI) on user_email.
    response = bookings_table.scan(FilterExpression=Attr('email').eq(session['user']))
    bookings = response.get('Items', [])
    return render_template("dashboard.html", name=session.get('name', 'User'), bookings=bookings)

# --- Service Pages ---
@app.route('/bus')
def bus(): return render_template("bus.html", buses=bus_data)

@app.route('/train')
def train(): return render_template("train.html", trains=train_data)

@app.route('/flight')
def flight(): return render_template("flight.html", flights=flight_data)

@app.route('/hotels')
def hotels(): return render_template("hotels.html", hotels=hotel_data)

@app.route('/seat/<transport_id>/<price>')
def seat(transport_id, price):
    if 'user' not in session: return redirect('/login')
    return render_template("seat.html", id=transport_id, price=price)

# ---------------- BOOKING FLOW ----------------

# Step 1: Review Booking (Triggered by Seat Selection)
@app.route('/book', methods=['POST'])
def book():
    if 'user' not in session: return redirect('/login')

    t_id = request.form['transport_id']
    seats = request.form['seat']
    price = request.form['price']
    
    # Create a temporary booking object in session
    session['booking_flow'] = {
        'transport_id': t_id,
        'details': get_transport_details(t_id),
        'seat': seats,
        'price': price,
        'date': str(datetime.date.today()) # Defaulting to today as date isn't passed from seat.html
    }
    
    return render_template("payment.html", booking=session['booking_flow'])

# Step 2: Final Payment (Triggered by Payment Page)
@app.route('/payment', methods=['POST'])
def payment():
    if 'user' not in session or 'booking_flow' not in session:
        return redirect('/dashboard')

    # Retrieve data from session
    booking_data = session['booking_flow']
    
    # Add payment details
    booking_id = str(uuid.uuid4())[:8]
    booking_data['booking_id'] = booking_id
    booking_data['email'] = session['user']
    booking_data['payment_method'] = request.form.get('method')
    booking_data['payment_reference'] = request.form.get('reference')
    booking_data['price'] = Decimal(booking_data['price']) # Convert for DynamoDB

    # Save to DynamoDB
    bookings_table.put_item(Item=booking_data)

    # Send SNS Notification
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="TravelGo Booking Confirmed",
            Message=f"Booking ID: {booking_id}\nDetails: {booking_data['details']}\nSeats: {booking_data['seat']}\nPrice: {booking_data['price']}"
        )
    except Exception as e:
        print(f"SNS Error: {e}")

    # Clear session booking data
    final_booking = booking_data.copy()
    session.pop('booking_flow', None)

    return render_template("ticket.html", booking=final_booking)

# ---------------- CANCEL / LOGOUT ----------------

@app.route('/remove_booking', methods=['POST'])
def remove_booking():
    if 'user' not in session: return redirect('/login')
    
    b_id = request.form['booking_id']
    bookings_table.delete_item(Key={'email': session['user'], 'booking_id': b_id})
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)