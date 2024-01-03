import os
import uuid
import json
import logging
import gc
import requests
import io
import string

from typing import Union
from flask import Flask, render_template, redirect, session, url_for, flash, request, current_app, send_file, jsonify
from google.cloud import storage
from werkzeug.utils import secure_filename
from google.appengine.api import app_identity
from google.appengine.api import mail
from requests_oauthlib import OAuth2Session

from data.db_connection import graph
# from models.load_models import loadModelClass

# Import OATH urls
from services.oath_urls import *

from services.utils import *
from services.accounts_services import *
from services.item_services import *
from services.course_services import *
from services.questions import *

app = Flask(__name__, subdomain_matching=True)
app.secret_key = os.getenv('SECRET_KEY','')

# Connect to db
graph.init_app(app) 


app.wsgi_app = google.appengine.api.wrap_wsgi_app(app.wsgi_app)
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT','')
app.config['SERVER_NAME'] = os.getenv('SERVER_NAME','classwise.local:8080')

@app.route('/_ah/warmup')
def warmup():
    """Warm up an instance of the app."""

    return jsonify({'status': 'success'})

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-store, must-revalidate"
    response.headers["Expires"] = 0
    return response

### Read in environment variables ###

cloud = os.getenv('CLOUD',False)
if not cloud:
    os.makedirs(uploadpath, exist_ok=True) 

betaCode = os.getenv('BETACODE','')

# file_bucket = os.getenv('FILE_BUCKET','scholarly_filebucket1')
file_bucket = os.getenv('FILE_BUCKET','')

# Root domain 
DOMAIN = ''

# Duke OATH
DUKE_CLIENT_ID = os.getenv('DUKE_CLIENT_ID','')
DUKE_CLIENT_SECRET = os.getenv('DUKE_CLIENT_SECRET','')

# Google OATH
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID','')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET','')

# Set properties for file uploads
uploadpath = os.path.join(os.path.dirname(__file__),'static/uploads') # LOCAL: Save the file to ./uploads
UPLOAD_FOLDER = uploadpath # LOCAL: Save the file to ./uploads
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

###

ALLOWED_EXTENSIONS = {'pdf','ppt','pptx'}
app.config['MAX_CONTENT_LENGTH'] = 26 * 1000 * 1000

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def send_mail(to_address,subject,html,body):
    sender_address = ''
    if html is not None:
        message = mail.EmailMessage(
            sender = sender_address,
            to = to_address,
            subject = subject,
            body = body,
            html = html
            )
    else:
        message = mail.EmailMessage(
            sender = sender_address,
            to = to_address,
            subject = subject,
            body = body
            )

    message.send()
    return

@app.route('/success.html')
def success():
    return render_template('accounts/success.html')

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/about')
def about():
    return render_template("about.html")

@app.route('/legal/privacypolicy')
def privacypolicy():
    return render_template("legal/privacypolicy.html")

@app.route('/legal/useragreement')
def useragreement():
    return render_template("legal/useragreement.html")    

@app.route('/home/support')
def facultySupport():
    return render_template("home/support.html")  


@app.route('/home/dashboard', methods = ['GET','POST'])
def dashboard(): 

    if "usr" in session:
        usr = session["usr"]
        
        if request.method=='POST':

            return render_template("home/dashboard.html",
                                )

        else:
            
                return render_template("home/dashboard.html",
                                    )

    else:
        return redirect(url_for("login_get"))


@app.route('/accounts/register', methods=['GET'])
def register_get():
    return render_template("accounts/register.html")

@app.route('/accounts/register', methods=['POST'])
def register_post():

    # Register via Google OAuth
    if request.form.get('googleSignin',False):
        print('registering via Google OAuth')
        return redirect(url_for("google_login"))

    # Register via SSO
    if request.form.get('ssoButton',False):
        print('registering via SSO')
        status = request.form.get('status_sso','student')
        university = request.form.get('university_sso','')
        if university == '':
            flash('Please select a university')
            return redirect(url_for("register_get"))
        session['university_sso'] = university
        session['status_sso'] = status
        return redirect(url_for("sso_login"))


    # Get the form data from register.html
    firstname = request.form.get('firstname')
    lastname = request.form.get('lastname')
    email = request.form.get('email').lower().strip()
    # username = request.form.get('username')
    password = request.form.get('password').strip()
    status = request.form.get('status','student')

    plan = request.form.get('plan','free')

    hasBetaCode = True


    # Check for blank fields in the registration form
    if not firstname or not lastname or not email or not password:
        flash("Please populate all the registration fields", "error")
        return render_template("accounts/register.html",firstname=firstname, lastname = lastname, email=email, password=password)

    # Check to make sure password is at least 8 characters
    if len(password) < 8:
        flash("Password must be at least 8 characters", "error")
        return render_template("accounts/register.html",firstname=firstname, lastname = lastname, email=email, password=password)

    # Create the user
    user = User(usr=email)
    res = user.load_user()
    if res is None:
        user.save_user(firstname,lastname,password,status,plan)
    else:
        flash("A user with that email or username already exists.")
        return render_template("accounts/register.html",firstname=firstname, lastname = lastname, email=email, password=password)

    # Generate token
    token = user.generate_confirmation_token()
    confirm_url = url_for('confirm_email', token=token, _external=True)
    html = render_template('messages/activate.html', confirm_url=confirm_url)
    subject = "Classwise: please confirm your email"
    body = ""

    if cloud:
        send_mail(to_address=email,subject=subject,html=html,body=body)

    flash('A confirmation email has been sent, please click the link to confirm your email.', 'success')

    if plan != 'free':
        # Send to payment page
        return render_template('home/addPayment.html')

    return redirect(url_for("login_get"))

@app.route('/accounts/forgotpassword', methods=['GET','POST'])
def forgot_password():
    if request.method=='POST':
        email = request.form.get('email').lower().strip()

        # Validate email
        user = User(usr=email)
        checkemail = user.load_user()
        if checkemail is None:
            flash("No account for that email address", "error")
            return render_template("accounts/login.html")
        else:
            # Generate token
            token = user.generate_confirmation_token(email)
            reset_url = url_for('reset_password', token=token, _external=True)
            html = render_template('messages/resetemail.html', reset_url=reset_url)
            subject = "Please reset your password on Classwise"
            body = ""

            if cloud:
                send_mail(to_address=email,subject=subject,html=html,body=body)

            flash('An email has been sent, please click the link in it to reset your password.', 'success')

            return redirect(url_for("login_get"))


    else:
        return render_template('accounts/forgotpassword.html')


@app.route('/emailreset/<token>')
def reset_password(token):
    try:
        email = confirm_token(token)
    except:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for("login_get"))
    
    return render_template("accounts/reset.html",token=token)

@app.route('/accounts/reset', methods=['GET','POST'])
def reset_page():
    if request.form.get('submitPassword',False):
        token = request.form.get('token')
        try:
            email = confirm_token(token)
        except:
            flash('The reset link is invalid or has expired.', 'danger')
            return redirect(url_for("login_get"))

        newpassword = request.form.get('newpassword')
        confirmpassword = request.form.get('confirmpassword')

        # Check if password and confirm match
        if newpassword != confirmpassword:
            flash("Passwords do not match")
            return render_template("accounts/reset.html",token=token)
    
        else:
            user = User(usr=email)
            completed = user.resetPassword(email,newpassword)
            if completed:
                flash('You have reset your password, please log in.', 'success')
                return redirect(url_for("login_get"))
            else:
                flash('An error has occurred, please try again.', 'danger')
                return redirect(url_for("login_get"))
        
    else:
        flash('Please click the link in your email', 'danger')
        return redirect(url_for("login_get"))



@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        email = confirm_token(token)
    except:
        flash('The confirmation link is invalid or has expired.', 'danger')
    user = User(usr=email)
    user.load_user()
    if user.confirmed:
        flash('Account already confirmed. Please login.', 'success')
    else:
        user.confirm_user()
        session["newuser"] = email
        flash('You have confirmed your account. Thanks!', 'success')

    return redirect(url_for("login_get"))


@app.route('/accounts/login', methods=['GET'])
def login_get(error=None):
    # Check if error occurred
    if error is not None:
        flash("An error has occurred. Please try to log in again", "error")
        return render_template("accounts/login.html")

    # Check if the user is already logged in.  if yes, redirect to dashboard
    elif "usr" in session:
        usr = session['usr']
        user = User(usr=usr)
        user.load_user()

        # if 'course' in session:
        #     session.pop('course')

        return redirect(url_for("dashboard"))

    else:
        return render_template("accounts/login.html")


@app.route('/accounts/login', methods=['POST'])
def login_post():

    # Log in via Google OAuth
    if request.form.get('googleSignin',False):
        print('logging in via Google OAuth')
        return redirect(url_for("google_login"))
    
    # If ssoButton, log in with SSO
    if request.form.get('ssoButton',False):
        university = request.form.get('university_sso','Duke University')
        status = request.form.get('status_sso')
        session['university_sso'] = university
        session['status_sso'] = status
        return redirect(url_for("sso_login"))
    
    # Otherwise, log in with email and password
    email = request.form['email']
    email = email.lower().strip()
    print('user logging in: ' + email)
    password = request.form['password']
    if not email or not password:
        return render_template("accounts/login.html", email=email, password=password)

    # Validate the user
    user = User(usr=email)
    
    try:
        loggedIn = user.login_user(password)
        if not loggedIn:
            flash("No account for that email address or the password is incorrect", "error")
            return render_template("accounts/login.html", email=email, password=password)
        print('successfully logged in')
    except Exception as e:
        print(e)
        flash("Cannot reach database server.  Please try again later", "error")
        return render_template("accounts/login.html", email=email, password=password)

    # Validate user has confirmed email
    user.load_user()
    confirmed = user.confirmed
    if confirmed == False:
        flash("Email has not yet been confirmed.  Please check your email and click the link to confirm your email address", "error")
        return render_template("accounts/login.html", email=email, password=password)

    # Log in user and create a user session
    usr = request.form["email"].lower().strip()
    session["usr"] = usr
    # if 'course' in session:
    #     session.pop('course')


    return redirect(url_for("dashboard"))
    
@app.route('/accounts/googlelogin', methods=['GET'])
def google_login():
    # Create an anti-forgery state token
    state = str(uuid.uuid4())
    # Specify the scope of the request.  In this case we want to retrieve the user's profile and email address
    scope = ['openid','https://www.googleapis.com/auth/userinfo.profile', 'https://www.googleapis.com/auth/userinfo.email']
    # Create a Google OAuth2Session object
    google = OAuth2Session(GOOGLE_CLIENT_ID, scope=scope, state=state, redirect_uri=GOOGLE_REDIRECT_URI)
    # Generate the authorization URL
    authorization_url, state = google.authorization_url(GOOGLE_AUTHORIZATION_BASE_URL, access_type="offline", prompt="select_account")
    # Store the state so the callback can verify the auth server response.
    session['oauth_state'] = state
    # Redirect to the authorization URL
    return redirect(authorization_url)

@app.route('/accounts/sso', methods=['GET'])
def sso_login():
    responseType = 'code'
    if 'university_sso' in session:
        university = session['university_sso']
    else:
        university = 'Duke University'
    if university == 'Duke University':
        client_id = DUKE_CLIENT_ID
        client_secret = DUKE_CLIENT_SECRET
        authorization_base_url = DUKE_AUTHORIZATION_BASE_URL
        redirect_uri = DUKE_REDIRECT_URI

    state = str(uuid.uuid4())
    SSO = OAuth2Session(client_id = client_id, state=state, redirect_uri=redirect_uri)
    authorization_url, state = SSO.authorization_url(authorization_base_url)
    session['oath_state'] = state
    return redirect(authorization_url)

@app.route('/accounts/googleauth', methods=['GET'])
def google_auth():
    # Callback for Google OAuth2
    expected_state = session['oauth_state']
    state = request.args.get('state', None)
    if state != expected_state:
        return redirect(url_for("login_get"))
    
    # Fetch the access token
    token_url = GOOGLE_TOKEN_URL
    google = OAuth2Session(GOOGLE_CLIENT_ID, state=state, redirect_uri=GOOGLE_REDIRECT_URI)
    response_url = request.url  
    if "http:" in response_url:
        response_url = "https:" + response_url[5:]
    token = google.fetch_token(token_url, client_secret=GOOGLE_CLIENT_SECRET, authorization_response=response_url)
    session['oauth_token'] = token
    # Get the user's profile information
    userInfo = google.get(GOOGLE_USERINFO_URL).json()
    email = userInfo['email']
    email = email.lower()
    print(email)
    session['userInfo'] = userInfo

    user = User(usr=email)
    user.load_user()
    userType = user.account_type
    # User not registered, need to complete registration
    if userType is None:
        # Must complete profile
        return redirect(url_for("complete_profile"))
        
    else:
        # Remove userInfo from session
        session.pop('userInfo', None)

        # Log in user and create a user session
        session['usr'] = email

        return redirect(url_for("dashboard"))

@app.route('/accounts/completeprofile', methods=['GET', 'POST'])
def complete_profile():
    if request.method == 'GET':
        # userInfo = session['userInfo']
        # email = userInfo['email']
        return render_template("accounts/completeprofile.html")
    
    else:
        userInfo = session['userInfo']
        email = userInfo['email']
        email = email.lower().strip()
        password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
        firstname = userInfo['given_name']
        lastname = userInfo['family_name']
        status = request.form.get('status','student')
        level = request.form.get('level','higherEd')
        state = request.form.get('state',None)
        plan = request.form.get('plan','free')
        if level == 'higherEd':
            university = request.form.get('university','')
        else:
            university = request.form.get('k12school','')

        hasBetaCode = True

        # # Check beta code if user is signing up as faculty
        # if status == 'faculty':
        #     userBetaCode = request.form.get('betaCode',False)
        #     if userBetaCode == betaCode:
        #         hasBetaCode = True
        #     elif userBetaCode != betaCode:
        #         flash("Please enter the correct code for the Classwise beta", "error")
        #         return render_template("accounts/completeprofile.html",states=states)

        #     hasBetaCode = True

        # Check to make sure school is provided
        if len(university) == 0:
            flash("Please enter your school", "error")
            return render_template("accounts/completeprofile.html')


        # Create the user
        user = User(usr=email)
        res = user.load_user()
        if res is None:
            user.save_user(firstname,lastname,password,status,plan)
        else:
            flash("A user with that email or username already exists.")
            return render_template("accounts/register.html")

        # Automatically confirm user
        user.confirm_user()

        # Remove userInfo and university from session
        session.pop('userInfo')

        # Log in user and create a user session
        session['usr'] = email
        
        return redirect(url_for("dashboard"))


@app.route('/accounts/auth', methods=['GET'])
def duke_auth():
    expected_state = session['oath_state']
    state = request.args.get('state', None)
    if state != expected_state:
        return redirect(url_for("login_get"))
    
    # Get correct token url and redirect uri
    university = session['university_sso']
    if university == 'Duke University':
        token_url = DUKE_TOKEN_URL
        redirect_uri = DUKE_REDIRECT_URI
        responseType = 'code'
        client_id = DUKE_CLIENT_ID
        client_secret = DUKE_CLIENT_SECRET
    
    SSO = OAuth2Session(client_id = client_id, state=state, redirect_uri=redirect_uri)
    response_url = request.url  
    if "http:" in response_url:
        response_url = "https:" + response_url[5:]
    token = SSO.fetch_token(token_url, client_secret=client_secret, authorization_response=response_url)
    session['oath_token'] = token
    userInfo = SSO.get(DUKE_USERINFO_URL)
    userInfo = userInfo.json()
    email = userInfo['email']
    email = email.lower().strip()
    print(email)
    session['usr'] = email

    user = User(usr=email)
    loaded = user.load_user()
    userType = user.account_type

    # User not registered, need to complete registration
    if userType is None:
        firstname = userInfo['given_name']
        lastname = userInfo['family_name']
        email = userInfo['email']
        email = email.lower().strip()
        password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
        hasBetaCode = True
        # plan = request.form.get('plan','free')
        plan = 'free'
        status = session['status_sso']

        # Create the user
        if not loaded:
            user.save_user(firstname,lastname,password,status,plan)
        else:
            flash("A user with that email or username already exists.")
            return render_template("accounts/register.html")

        # Automatically confirm user
        user.confirm_user()

        # Remove userInfo and university from session
        # session.pop('userInfo')
        session.pop('university_sso')
        session.pop('status_sso')

        # Log in user and create a user session
        session['usr'] = email
        user.load_user()

        return redirect(url_for("dashboard"))

    else:
        # Remove university and status from session
        session.pop('university_sso')
        session.pop('status_sso')

        # if 'course' in session:
        #     session.pop('course')

        return redirect(url_for("dashboard"))
        


@app.route('/accounts/profile', methods=['GET'])
def profile_get():
    # Make sure the user has an active session.  If not, redirect to the login page.
    if "usr" in session:
        usr = session["usr"]
        user = User()
        loaded = user.load_user(usr)

        if loaded is not None:
            if user.level is None:
                user['level'] = 'higherEd'

            if user.account_type == 'faculty':
                return render_template("accounts/profile_faculty.html", user = user, states=states)
            else:
                return render_template("accounts/profile_student.html", user = user, states=states)
        else:
            return redirect(url_for("login_get"))
    else:
        return redirect(url_for("login_get"))


@app.route('/accounts/profile', methods=['POST'])
def profile_post():
    # Make sure the user has an active session.  If not, redirect to the login page.
    if "usr" in session:
        usr = session["usr"]
        firstname = request.form.get('firstname')
        lastname = request.form.get('lastname')
        email = request.form.get('email').lower().strip()
        # username = request.form.get('username')

        # Edit user
        # user = edit_user(usr,firstname, lastname, email,level, state, university)
        user = User(usr=usr)
        loaded = user.load_user()
        if loaded is not None:

            # Update session if email has changed
            if email != usr:
                session["usr"] = user['email']

            if user['account_type'] == 'faculty':
                return render_template("accounts/profile_faculty.html", user = user, states=states)
            else:
                return render_template("accounts/profile_student.html", user = user, states=states)
        else:
            return redirect(url_for("login_get"))
        
    else:
        return redirect(url_for("login_get"))


@app.route('/accounts/logout')
def logout():
    session.pop("usr", None)
    session.pop("course", None)
    flash("You have successfully been logged out.", "info")
    return redirect(url_for("login_get"))

@app.route('/accounts/deleteAccount', methods=['GET'])
def delete_account_get():
    usr = session["usr"]
    user = User(usr=usr)
    done = user.delete_user()
    if done:
        session.pop("usr", None)
        session.pop("course", None)
        return redirect(url_for("login_get"))
    
@app.errorhandler(500)
def server_error(e: Union[Exception, int]) -> str:
    logging.exception('An error occurred during a request: {}.'.format(e))

    
    return redirect(url_for("login_get",error=e))

if __name__ == '__main__':
    app.run()