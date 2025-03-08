import pymysql
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

# Parse the public URL
url = urlparse(os.getenv('MYSQL_PUBLIC_URL'))
connection_params = {
    'host': url.hostname,
    'user': url.username,
    'password': url.password,
    'database': url.path[1:],  # Remove leading '/'
    'port': url.port
}

# Print connection parameters for debugging
print("Connection parameters:", connection_params)

# Drop existing tables
def drop_tables(cursor):
    tables = [
        'ai_verification_logs',
        'satellite_data',
        'transactions',
        'carbon_credits',
        'carbon_assessments',
        'projects',
        'users'
    ]
    for table in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")

# Create tables
def setup_database():
    try:
        conn = pymysql.connect(**connection_params)
        cursor = conn.cursor()
        
        # Drop existing tables
        drop_tables(cursor)
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(200) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_type ENUM('individual', 'organization') NOT NULL,
                profile_img_url VARCHAR(255),
                verification_status ENUM('pending', 'verified') DEFAULT 'pending'
            )
        ''')
        
        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                project_name VARCHAR(200) NOT NULL,
                project_type ENUM('forestry', 'agriculture', 'agroforestry', 'wetland', 'other') NOT NULL,
                location_lat DECIMAL(10, 8) NOT NULL,
                location_lng DECIMAL(11, 8) NOT NULL,
                area_size DECIMAL(10, 2) NOT NULL,
                area_unit ENUM('hectares', 'acres') NOT NULL,
                description TEXT,
                start_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status ENUM('registered', 'assessing', 'verified', 'active', 'completed') DEFAULT 'registered',
                boundary_geojson JSON,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Carbon Assessments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS carbon_assessments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                assessment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                carbon_estimate DECIMAL(12, 2) NOT NULL,
                confidence_score DECIMAL(5, 2) NOT NULL,
                methodology VARCHAR(100) NOT NULL,
                data_sources JSON NOT NULL,
                ai_model_version VARCHAR(50) NOT NULL,
                verification_status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
                report_url VARCHAR(255),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')
        
        # Carbon Credits table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS carbon_credits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                assessment_id INT NOT NULL,
                credit_amount DECIMAL(12, 2) NOT NULL,
                issuance_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expiry_date DATE,
                certificate_id VARCHAR(100) UNIQUE NOT NULL,
                status ENUM('available', 'reserved', 'sold', 'expired') DEFAULT 'available',
                price_per_credit DECIMAL(10, 2),
                verification_document_url VARCHAR(255),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (assessment_id) REFERENCES carbon_assessments(id) ON DELETE CASCADE
            )
        ''')
        
        # Transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                credit_id INT NOT NULL,
                buyer_id INT NOT NULL,
                seller_id INT NOT NULL,
                amount DECIMAL(12, 2) NOT NULL,
                price_per_unit DECIMAL(10, 2) NOT NULL,
                total_price DECIMAL(12, 2) NOT NULL,
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status ENUM('pending', 'completed', 'cancelled') DEFAULT 'pending',
                FOREIGN KEY (credit_id) REFERENCES carbon_credits(id) ON DELETE CASCADE,
                FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Satellite Monitoring Data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS satellite_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                capture_date DATE NOT NULL,
                ndvi_value DECIMAL(5, 4),
                land_cover_classification VARCHAR(50),
                cloud_cover_percentage DECIMAL(5, 2),
                source VARCHAR(50) NOT NULL,
                raw_data_url VARCHAR(255),
                processed_data_url VARCHAR(255),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')
        
        # AI Verification Logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_verification_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                assessment_id INT,
                verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model_used VARCHAR(100) NOT NULL,
                input_data JSON,
                output_result JSON,
                confidence_score DECIMAL(5, 2),
                verification_type ENUM('initial', 'periodic', 'final') NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (assessment_id) REFERENCES carbon_assessments(id) ON DELETE SET NULL
            )
        ''')
        
        # Insert dummy data
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, user_type, verification_status)
            VALUES 
            ('john_doe', 'john@example.com', 'hashed_password', 'individual', 'verified'),
            ('jane_doe', 'jane@example.com', 'hashed_password', 'organization', 'verified')
        ''')
        
        cursor.execute('''
            INSERT INTO projects (user_id, project_name, project_type, location_lat, location_lng, area_size, area_unit, description, start_date, status, boundary_geojson)
            VALUES 
            (1, 'Forest Conservation', 'forestry', 34.052235, -118.243683, 100.00, 'hectares', 'A project to conserve forest area.', '2023-01-01', 'registered', '{}'),
            (2, 'Wetland Restoration', 'wetland', 36.778259, -119.417931, 50.00, 'acres', 'A project to restore wetland.', '2023-02-01', 'registered', '{}')
        ''')
        
        cursor.execute('''
            INSERT INTO carbon_assessments (project_id, carbon_estimate, confidence_score, methodology, data_sources, ai_model_version, verification_status)
            VALUES 
            (1, 5000.00, 95.00, 'AI-based assessment', '{"source": "satellite"}', 'gpt-4', 'approved'),
            (2, 3000.00, 90.00, 'AI-based assessment', '{"source": "satellite"}', 'gpt-4', 'approved')
        ''')
        
        cursor.execute('''
            INSERT INTO carbon_credits (project_id, assessment_id, credit_amount, expiry_date, certificate_id, status, price_per_credit, verification_document_url)
            VALUES 
            (1, 1, 5000.00, '2028-01-01', 'CC-1-abc123', 'available', 25.00, '/reports/1_20230101.pdf'),
            (2, 2, 3000.00, '2028-02-01', 'CC-2-def456', 'available', 30.00, '/reports/2_20230201.pdf')
        ''')
        
        cursor.execute('''
            INSERT INTO transactions (credit_id, buyer_id, seller_id, amount, price_per_unit, total_price, status)
            VALUES 
            (1, 2, 1, 1000.00, 25.00, 25000.00, 'completed'),
            (2, 1, 2, 500.00, 30.00, 15000.00, 'completed')
        ''')
        
        cursor.execute('''
            INSERT INTO satellite_data (project_id, capture_date, ndvi_value, land_cover_classification, cloud_cover_percentage, source, raw_data_url, processed_data_url)
            VALUES 
            (1, '2023-01-15', 0.75, 'Forest', 10.00, 'Sentinel-2', 'http://example.com/raw1', 'http://example.com/processed1'),
            (2, '2023-02-15', 0.65, 'Wetland', 5.00, 'Sentinel-2', 'http://example.com/raw2', 'http://example.com/processed2')
        ''')
        
        cursor.execute('''
            INSERT INTO ai_verification_logs (project_id, assessment_id, model_used, input_data, output_result, confidence_score, verification_type)
            VALUES 
            (1, 1, 'gpt-4', '{"project_type": "forestry"}', '{"carbon_estimate": 5000.00}', 95.00, 'initial'),
            (2, 2, 'gpt-4', '{"project_type": "wetland"}', '{"carbon_estimate": 3000.00}', 90.00, 'initial')
        ''')
        
        conn.commit()
        print("Database setup and dummy data insertion completed successfully")
        
    except Exception as e:
        print(f"Database setup error: {e}")
        
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    setup_database()