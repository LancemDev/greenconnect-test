from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import pymysql
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from openai_service import analyze_project, generate_assessment_report
from satellite_service import fetch_satellite_imagery, analyze_satellite_data
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(16))

# Parse the public URL
url = urlparse(os.getenv('MYSQL_PUBLIC_URL'))
db_config = {
    'host': url.hostname,
    'user': url.username,
    'password': url.password,
    'database': url.path[1:],  # Remove leading '/'
    'port': url.port,
    'cursorclass': pymysql.cursors.DictCursor
}

# Database connection function
def get_db_connection():
    return pymysql.connect(**db_config)

# Check if user is logged in
def is_logged_in():
    return 'user_id' in session

# Home page
@app.route('/')
def index():
    return render_template('index.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
                
                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    flash('Login successful!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid email or password', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        finally:
            conn.close()
            
    return render_template('login.html')

# User registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        
        # Hash the password
        password_hash = generate_password_hash(password)
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Check if user already exists
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash('Email already registered', 'error')
                    return render_template('register.html')
                
                # Insert new user
                cursor.execute(
                    "INSERT INTO users (username, email, password_hash, user_type) VALUES (%s, %s, %s, %s)",
                    (username, email, password_hash, user_type)
                )
                conn.commit()
                
                # Get the user ID for session
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
                
                # Set session
                session['user_id'] = user['id']
                session['username'] = username
                
                flash('Registration successful!', 'success')
                return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        finally:
            conn.close()
            
    return render_template('register.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# User dashboard
@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        flash('Please login to access your dashboard', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cursor:
            # Get user's projects
            cursor.execute("""
                SELECT * FROM projects 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            """, (user_id,))
            projects = cursor.fetchall()
            
            # Get carbon credits
            cursor.execute("""
                SELECT cc.*, p.project_name 
                FROM carbon_credits cc
                JOIN projects p ON cc.project_id = p.id
                WHERE p.user_id = %s
                ORDER BY issuance_date DESC
            """, (user_id,))
            credits = cursor.fetchall()
            
            # Get recent transactions
            cursor.execute("""
                SELECT t.*, cc.certificate_id, p.project_name
                FROM transactions t
                JOIN carbon_credits cc ON t.credit_id = cc.id
                JOIN projects p ON cc.project_id = p.id
                WHERE t.seller_id = %s OR t.buyer_id = %s
                ORDER BY transaction_date DESC
                LIMIT 5
            """, (user_id, user_id))
            transactions = cursor.fetchall()
            
            return render_template('dashboard.html', 
                                  projects=projects, 
                                  credits=credits, 
                                  transactions=transactions)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return render_template('dashboard.html', projects=[], credits=[], transactions=[])
    finally:
        conn.close()

# Project registration
@app.route('/project/register', methods=['GET', 'POST'])
def register_project():
    if not is_logged_in():
        flash('Please login to register a project', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        user_id = session['user_id']
        project_name = request.form['project_name']
        project_type = request.form['project_type']
        lat = request.form['latitude']
        lng = request.form['longitude']
        area_size = request.form['area_size']
        area_unit = request.form['area_unit']
        description = request.form['description']
        start_date = request.form['start_date']
        boundary_geojson = request.form.get('boundary_geojson', '{}')
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO projects 
                    (user_id, project_name, project_type, location_lat, location_lng, 
                     area_size, area_unit, description, start_date, boundary_geojson)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, project_name, project_type, lat, lng, 
                      area_size, area_unit, description, start_date, boundary_geojson))
                conn.commit()
                
                # Get the project ID
                cursor.execute("SELECT LAST_INSERT_ID() as id")
                project_id = cursor.fetchone()['id']
                
                flash('Project registered successfully!', 'success')
                
                # Fetch satellite imagery
                satellite_data = fetch_satellite_imagery(float(lat), float(lng), float(area_size), area_unit)
                
                # Store satellite data
                cursor.execute("""
                    INSERT INTO satellite_data 
                    (project_id, capture_date, ndvi_value, land_cover_classification, 
                     cloud_cover_percentage, source, raw_data_url, processed_data_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    project_id, 
                    datetime.now().strftime('%Y-%m-%d'),
                    satellite_data.get('ndvi_value', 0),
                    satellite_data.get('land_cover_classification', 'Unknown'),
                    satellite_data.get('cloud_cover_percentage', 0),
                    satellite_data.get('source', 'Sentinel-2'),
                    satellite_data.get('raw_data_url', ''),
                    satellite_data.get('processed_data_url', '')
                ))
                conn.commit()
                
                # Analyze project with OpenAI
                project_data = {
                    'project_type': project_type,
                    'area_size': float(area_size),
                    'area_unit': area_unit,
                    'satellite_data': satellite_data
                }
                
                assessment_result = analyze_project(project_data)
                
                # Store assessment result
                cursor.execute("""
                    INSERT INTO carbon_assessments 
                    (project_id, carbon_estimate, confidence_score, methodology, 
                     data_sources, ai_model_version, verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    project_id,
                    assessment_result.get('carbon_estimate', 0.0),
                    assessment_result.get('confidence_score', 0.0),
                    assessment_result.get('methodology', 'AI-based assessment'),
                    json.dumps(assessment_result.get('data_sources', {})),
                    assessment_result.get('model_version', 'gpt-4'),
                    'pending'
                ))
                conn.commit()
                
                # Get the assessment ID
                cursor.execute("SELECT LAST_INSERT_ID() as id")
                assessment_id = cursor.fetchone()['id']
                
                # Log AI verification
                cursor.execute("""
                    INSERT INTO ai_verification_logs 
                    (project_id, assessment_id, model_used, input_data, 
                     output_result, confidence_score, verification_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    project_id,
                    assessment_id,
                    assessment_result.get('model_version', 'gpt-4'),
                    json.dumps(project_data),
                    json.dumps(assessment_result),
                    assessment_result.get('confidence_score', 0.0),
                    'initial'
                ))
                conn.commit()
                
                # Update project status based on assessment result
                cursor.execute("""
                    UPDATE projects 
                    SET status = 'assessing' 
                    WHERE id = %s
                """, (project_id,))
                conn.commit()
                
                return redirect(url_for('project_assessment', project_id=project_id))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        finally:
            conn.close()
            
    return render_template('register_project.html')

# Project assessment
@app.route('/project/<int:project_id>/assessment')
def project_assessment(project_id):
    if not is_logged_in():
        flash('Please login to view project assessment', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM projects 
                WHERE id = %s AND user_id = %s
            """, (project_id, session['user_id']))
            project = cursor.fetchone()
            
            if not project:
                flash('Project not found or unauthorized', 'error')
                return redirect(url_for('dashboard'))
            
            # Update project status to assessing
            cursor.execute("""
                UPDATE projects 
                SET status = 'assessing' 
                WHERE id = %s
            """, (project_id,))
            conn.commit()
            
            # Fetch satellite imagery (this would be async in production)
            try:
                satellite_data = fetch_satellite_imagery(
                    float(project['location_lat']), 
                    float(project['location_lng']),
                    float(project['area_size']),
                    project['area_unit']
                )
                
                # Store satellite data
                cursor.execute("""
                    INSERT INTO satellite_data 
                    (project_id, capture_date, ndvi_value, land_cover_classification, 
                     cloud_cover_percentage, source, raw_data_url, processed_data_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    project_id, 
                    datetime.now().strftime('%Y-%m-%d'),
                    satellite_data.get('ndvi_value', 0),
                    satellite_data.get('land_cover_classification', 'Unknown'),
                    satellite_data.get('cloud_cover_percentage', 0),
                    satellite_data.get('source', 'Sentinel-2'),
                    satellite_data.get('raw_data_url', ''),
                    satellite_data.get('processed_data_url', '')
                ))
                conn.commit()
                
                # Analyze project with OpenAI (again, would be async in production)
                project_data = {
                    'project_type': project['project_type'],
                    'area_size': float(project['area_size']),
                    'area_unit': project['area_unit'],
                    'satellite_data': satellite_data
                }
                
                assessment_result = analyze_project(project_data)
                
                # Store assessment result
                cursor.execute("""
                    INSERT INTO carbon_assessments 
                    (project_id, carbon_estimate, confidence_score, methodology, 
                     data_sources, ai_model_version, verification_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    project_id,
                    assessment_result.get('carbon_estimate', 0),
                    assessment_result.get('confidence_score', 0),
                    assessment_result.get('methodology', 'AI-based assessment'),
                    json.dumps(assessment_result.get('data_sources', {})),
                    assessment_result.get('model_version', 'gpt-4'),
                    'pending'
                ))
                conn.commit()
                
                # Get the assessment ID
                cursor.execute("SELECT LAST_INSERT_ID() as id")
                assessment_id = cursor.fetchone()['id']
                
                # Log AI verification
                cursor.execute("""
                    INSERT INTO ai_verification_logs 
                    (project_id, assessment_id, model_used, input_data, 
                     output_result, confidence_score, verification_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    project_id,
                    assessment_id,
                    assessment_result.get('model_version', 'gpt-4'),
                    json.dumps(project_data),
                    json.dumps(assessment_result),
                    assessment_result.get('confidence_score', 0),
                    'initial'
                ))
                conn.commit()
                
                # Get the latest assessment
                cursor.execute("""
                    SELECT * FROM carbon_assessments 
                    WHERE project_id = %s 
                    ORDER BY assessment_date DESC 
                    LIMIT 1
                """, (project_id,))
                assessment = cursor.fetchone()
                
                return render_template('assessment.html', 
                                      project=project, 
                                      assessment=assessment,
                                      satellite_data=satellite_data)
                
            except Exception as e:
                flash(f'Assessment error: {str(e)}', 'error')
                return render_template('assessment.html', 
                                      project=project, 
                                      assessment=None,
                                      satellite_data=None)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# Generate verification report
@app.route('/project/<int:project_id>/generate-report')
def generate_report(project_id):
    if not is_logged_in():
        flash('Please login to generate a report', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.*, ca.* 
                FROM projects p
                JOIN carbon_assessments ca ON p.id = ca.project_id
                WHERE p.id = %s AND p.user_id = %s
                ORDER BY ca.assessment_date DESC
                LIMIT 1
            """, (project_id, session['user_id']))
            project_data = cursor.fetchone()
            
            if not project_data:
                flash('Project not found or unauthorized', 'error')
                return redirect(url_for('dashboard'))
            
            # Generate report
            report_data = generate_assessment_report(project_data)
            
            # Update assessment with report URL
            report_url = f"/reports/{project_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
            cursor.execute("""
                UPDATE carbon_assessments 
                SET report_url = %s, verification_status = 'approved' 
                WHERE id = %s
            """, (report_url, project_data['id']))
            
            # Update project status
            cursor.execute("""
                UPDATE projects 
                SET status = 'verified' 
                WHERE id = %s
            """, (project_id,))
            
            # Generate carbon credits
            certificate_id = f"CC-{project_id}-{secrets.token_hex(4)}"
            credit_amount = float(project_data['carbon_estimate'])
            expiry_date = (datetime.now() + timedelta(days=365*5)).strftime('%Y-%m-%d')
            
            cursor.execute("""
                INSERT INTO carbon_credits 
                (project_id, assessment_id, credit_amount, expiry_date, 
                 certificate_id, status, price_per_credit, verification_document_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                project_id,
                project_data['id'],
                credit_amount,
                expiry_date,
                certificate_id,
                'available',
                25.00,  # Default price per credit
                report_url
            ))
            
            conn.commit()
            flash('Verification report generated and carbon credits issued!', 'success')
            return redirect(url_for('project_details', project_id=project_id))
            
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# Project details
@app.route('/project/<int:project_id>')
def project_details(project_id):
    if not is_logged_in():
        flash('Please login to view project details', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM projects 
                WHERE id = %s AND user_id = %s
            """, (project_id, session['user_id']))
            project = cursor.fetchone()
            
            if not project:
                flash('Project not found or unauthorized', 'error')
                return redirect(url_for('dashboard'))
            
            # Get assessments
            cursor.execute("""
                SELECT * FROM carbon_assessments 
                WHERE project_id = %s 
                ORDER BY assessment_date DESC
            """, (project_id,))
            assessments = cursor.fetchall()
            
            # Get carbon credits
            cursor.execute("""
                SELECT * FROM carbon_credits 
                WHERE project_id = %s 
                ORDER BY issuance_date DESC
            """, (project_id,))
            credits = cursor.fetchall()
            
            # Get satellite data
            cursor.execute("""
                SELECT * FROM satellite_data 
                WHERE project_id = %s 
                ORDER BY capture_date DESC
            """, (project_id,))
            satellite_data = cursor.fetchall()
            
            return render_template('project_details.html', 
                                  project=project, 
                                  assessments=assessments,
                                  credits=credits,
                                  satellite_data=satellite_data)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    finally:
        conn.close()

# Marketplace
@app.route('/marketplace')
def marketplace():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT cc.*, p.project_name, p.project_type, u.username as seller_name
                FROM carbon_credits cc
                JOIN projects p ON cc.project_id = p.id
                JOIN users u ON p.user_id = u.id
                WHERE cc.status = 'available'
                ORDER BY cc.issuance_date DESC
            """)
            available_credits = cursor.fetchall()
            
            return render_template('marketplace.html', credits=available_credits)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return render_template('marketplace.html', credits=[])
    finally:
        conn.close()

# Buy credits
@app.route('/marketplace/buy/<int:credit_id>', methods=['GET', 'POST'])
def buy_credit(credit_id):
    if not is_logged_in():
        flash('Please login to purchase credits', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT cc.*, p.user_id as seller_id, p.project_name
                FROM carbon_credits cc
                JOIN projects p ON cc.project_id = p.id
                WHERE cc.id = %s AND cc.status = 'available'
            """, (credit_id,))
            credit = cursor.fetchone()
            
            if not credit:
                flash('Credit not available for purchase', 'error')
                return redirect(url_for('marketplace'))
            
            if request.method == 'POST':
                buyer_id = session['user_id']
                seller_id = credit['seller_id']
                amount = float(request.form['amount'])
                price_per_unit = float(credit['price_per_credit'])
                total_price = amount * price_per_unit
                
                # Create transaction
                cursor.execute("""
                    INSERT INTO transactions 
                    (credit_id, buyer_id, seller_id, amount, price_per_unit, total_price, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (credit_id, buyer_id, seller_id, amount, price_per_unit, total_price, 'completed'))
                
                # Update credit status if all purchased
                if amount >= credit['credit_amount']:
                    cursor.execute("""
                        UPDATE carbon_credits 
                        SET status = 'sold' 
                        WHERE id = %s
                    """, (credit_id,))
                else:
                    # Split the credit
                    new_amount = credit['credit_amount'] - amount
                    cursor.execute("""
                        UPDATE carbon_credits 
                        SET credit_amount = %s 
                        WHERE id = %s
                    """, (amount, credit_id))
                    
                    # Create new credit for remaining amount
                    new_certificate_id = f"CC-{credit['project_id']}-{secrets.token_hex(4)}"
                    cursor.execute("""
                        INSERT INTO carbon_credits 
                        (project_id, assessment_id, credit_amount, issuance_date, expiry_date, 
                         certificate_id, status, price_per_credit, verification_document_url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        credit['project_id'],
                        credit['assessment_id'],
                        new_amount,
                        credit['issuance_date'],
                        credit['expiry_date'],
                        new_certificate_id,
                        'available',
                        credit['price_per_credit'],
                        credit['verification_document_url']
                    ))
                
                conn.commit()
                flash('Credit purchase successful!', 'success')
                return redirect(url_for('dashboard'))
            
            return render_template('buy_credit.html', credit=credit)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('marketplace'))
    finally:
        conn.close()

# Information center
@app.route('/info-center')
def info_center():
    return render_template('info_center.html')

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))