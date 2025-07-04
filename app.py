from flask import Flask, render_template, request, redirect, url_for, session
import boto3
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

app = Flask(__name__)

# ---------------- AWS SETUP ----------------
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sns = boto3.client('sns', region_name='us-east-1')
sns_topic_arn = 'arn:aws:sns:us-east-1:588738595058:Medtrack:d10a7f8f-f58f-4b5c-a194-d6b5b2de338c'  # Update this

# Tables
users_table = dynamodb.Table('Users')
appointments_table = dynamodb.Table('Appointments')


# ---------------- ROUTES ----------------

@app.route('/')
def index():
    return render_template('index.html')


# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        email = data['email']
        username = data['username']
        password = generate_password_hash(data['password'])
        role = data['role']
        disease = data.get('disease', '')
        specialization = data.get('specialization', '')

        # Check if user exists
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            return render_template('register.html', error='Email already registered')

        users_table.put_item(Item={
            'email': email,
            'username': username,
            'password': password,
            'role': role,
            'disease': disease,
            'specialization': specialization
        })

        return redirect('/login')

    return render_template('register.html')


# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        response = users_table.get_item(Key={'email': email})
        user = response.get('Item')

        if user and check_password_hash(user['password'], password):
            session['email'] = email
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect('/dashboard')
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')


# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect('/login')

    if session['role'] == 'doctor':
        response = appointments_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('doctor').eq(session['username'])
        )
        appointments = response.get('Items', [])
        return render_template('doctor_dashboard.html', username=session['username'], appointments=appointments)

    else:
        response = appointments_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(session['username'])
        )
        appointments = response.get('Items', [])
        return render_template('dashboard.html', username=session['username'], appointments=appointments)


# ---------- PROFILE ----------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'username' not in session:
        return redirect('/login')

    email = session['email']
    response = users_table.get_item(Key={'email': email})
    user = response.get('Item')
    message = ''

    if request.method == 'POST':
        current_pw = request.form['current_password']
        new_pw = request.form['new_password']

        if check_password_hash(user['password'], current_pw):
            new_hashed = generate_password_hash(new_pw)
            users_table.update_item(
                Key={'email': email},
                UpdateExpression="SET password = :p",
                ExpressionAttributeValues={':p': new_hashed}
            )
            message = "Password updated successfully!"
        else:
            message = "Incorrect current password."

    # Count appointments
    appts = appointments_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(session['username'])
    ).get('Items', [])

    return render_template('profile.html', username=user['username'],
                           role=user['role'], disease=user.get('disease', ''),
                           specialization=user.get('specialization', ''),
                           appt_count=len(appts), message=message)


# ---------- BOOK APPOINTMENT ----------
@app.route('/book', methods=['GET', 'POST'])
def book():
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'POST':
        doctor = request.form['doctor']
        appt_date = request.form['date']
        time = request.form['time']
        reason = request.form['reason']

        appointments_table.put_item(Item={
            'id': str(uuid.uuid4()),
            'username': session['username'],
            'doctor': doctor,
            'date': appt_date,
            'time': time,
            'reason': reason
        })

        # Notify via SNS
        try:
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject="New Appointment",
                Message=f"{session['username']} booked with Dr. {doctor} on {appt_date} at {time}"
            )
        except Exception as e:
            print("SNS error:", e)

        return render_template('confirmation.html', doctor=doctor, date=appt_date, time=time)

    return render_template('book.html', current_date=date.today())


# ---------- PRESCRIBE ----------
@app.route('/prescribe/<string:appt_id>', methods=['GET', 'POST'])
def prescribe(appt_id):
    if 'username' not in session or session['role'] != 'doctor':
        return redirect('/login')

    response = appointments_table.get_item(Key={'id': appt_id})
    appt = response.get('Item')

    if request.method == 'POST':
        diagnosis = request.form['diagnosis']
        prescription = request.form['prescription']

        appointments_table.update_item(
            Key={'id': appt_id},
            UpdateExpression="SET diagnosis = :d, prescription = :p",
            ExpressionAttributeValues={':d': diagnosis, ':p': prescription}
        )
        return redirect('/dashboard')

    return render_template('prescribe.html', appt_id=appt_id, appt=appt)


# ---------- DELETE ----------
@app.route('/delete/<string:appt_id>')
def delete_appointment(appt_id):
    if 'username' not in session:
        return redirect('/login')

    appointments_table.delete_item(Key={'id': appt_id})
    return redirect('/dashboard')


# ---------- EDIT ----------
@app.route('/edit/<string:appt_id>', methods=['GET', 'POST'])
def edit_appointment(appt_id):
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'POST':
        doctor = request.form['doctor']
        date_val = request.form['date']
        time_val = request.form['time']
        reason = request.form['reason']

        appointments_table.update_item(
            Key={'id': appt_id},
            UpdateExpression="SET doctor = :d, date = :dt, time = :t, reason = :r",
            ExpressionAttributeValues={
                ':d': doctor, ':dt': date_val, ':t': time_val, ':r': reason
            }
        )
        return redirect('/dashboard')

    response = appointments_table.get_item(Key={'id': appt_id})
    appt = response.get('Item')
    return render_template('edit.html', appt=appt, appt_id=appt_id, current_date=date.today())


# ---------- ABOUT US ----------
@app.route('/aboutus')
def aboutus():
    return render_template('aboutus.html')


# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ---------- RUN APP ----------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
