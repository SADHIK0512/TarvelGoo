from flask import Flask, render_template, request, redirect, session
import boto3
import uuid
from decimal import Decimal

app = Flask(__name__)
app.secret_key = "travelgo_secret"

# ---------------- AWS CONNECTION (IAM ROLE BASED) ----------------
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
sns = boto3.client('sns', region_name='ap-south-1')

users_table = dynamodb.Table('travel-Users')
bookings_table = dynamodb.Table('Bookings')

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

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template("index.html")


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users_table.put_item(
            Item={
                'email': request.form['email'],
                'name': request.form['name'],
                'password': request.form['password']
            }
        )
        return redirect('/login')

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        response = users_table.get_item(Key={'email': request.form['email']})
        user = response.get('Item')

        if user and user['password'] == request.form['password']:
            session['user'] = user['email']
            return redirect('/dashboard')

        return "Invalid Credentials"

    return render_template("login.html")


# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    # Fetch only logged-in user's bookings
    response = bookings_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(session['user'])
    )

    bookings = response.get('Items', [])
    return render_template("dashboard.html", bookings=bookings)


# ---------------- BUS ----------------
@app.route('/bus')
def bus():
    return render_template("bus.html", buses=bus_data)


# ---------------- TRAIN ----------------
@app.route('/train')
def train():
    return render_template("train.html", trains=train_data)


# ---------------- FLIGHT ----------------
@app.route('/flight')
def flight():
    return render_template("flight.html", flights=flight_data)


# ---------------- HOTELS ----------------
@app.route('/hotels')
def hotels():
    return render_template("hotels.html", hotels=hotel_data)


# ---------------- SEAT SELECTION ----------------
@app.route('/seat/<transport_id>/<price>')
def seat(transport_id, price):
    if 'user' not in session:
        return redirect('/login')

    return render_template("seat.html", id=transport_id, price=price)


# ---------------- PAYMENT ----------------
@app.route('/payment', methods=['POST'])
def payment():
    if 'user' not in session:
        return redirect('/login')

    booking_id = str(uuid.uuid4())

    item = {
        'email': session['user'],
        'booking_id': booking_id,
        'transport_id': request.form['transport_id'],
        'seat': request.form['seat'],
        'price': Decimal(request.form['price'])
    }

    bookings_table.put_item(Item=item)

    # SNS Notification
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="TravelGo Booking Confirmed",
        Message=f"""
Booking Successful!

Booking ID: {booking_id}
Transport: {request.form['transport_id']}
Seat: {request.form['seat']}
Price: ₹{request.form['price']}
"""
    )

    return render_template("ticket.html", booking=item)


# ---------------- CANCEL BOOKING ----------------
@app.route('/cancel/<booking_id>', methods=['POST'])
def cancel(booking_id):
    if 'user' not in session:
        return redirect('/login')

    bookings_table.delete_item(
        Key={
            'email': session['user'],
            'booking_id': booking_id
        }
    )

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject="TravelGo Booking Cancelled",
        Message=f"Booking ID {booking_id} has been cancelled."
    )

    return redirect('/dashboard')


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
