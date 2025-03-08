import os
import json
from openai import OpenAI
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure OpenAI API client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_project(project_data):
    """
    Analyze a carbon sequestration project using OpenAI's GPT models.
    
    Args:
        project_data (dict): Project details including type, size, and satellite data
        
    Returns:
        dict: Assessment results including carbon estimate and confidence score
    """
    try:
        prompt = f"""
        Analyze the following carbon sequestration project and provide a detailed assessment:
        
        Project Type: {project_data['project_type']}
        Area Size: {project_data['area_size']} {project_data['area_unit']}
        
        Satellite Data:
        - NDVI Value: {project_data['satellite_data'].get('ndvi_value', 'N/A')}
        - Land Cover Classification: {project_data['satellite_data'].get('land_cover_classification', 'N/A')}
        - Cloud Cover: {project_data['satellite_data'].get('cloud_cover_percentage', 'N/A')}%
        
        Based on this information, please provide:
        1. Estimated carbon sequestration potential (in tons CO2e/year)
        2. Confidence score (0-100%)
        3. Recommended methodology
        4. Key data sources to consider
        5. Potential risks and limitations
        
        Format your response as a JSON object with the following keys:
        carbon_estimate, confidence_score, methodology, data_sources, risks, recommendations
        """
        
        logger.info("Sending project data to OpenAI for analysis: %s", project_data)
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert carbon analyst specializing in nature-based solutions. Provide accurate, science-based assessments using available data."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        logger.info("Received response from OpenAI: %s", response)
        
        # Extract the JSON response
        result_text = response.choices[0].message.content
        logger.info("Parsed result from OpenAI response: %s", result_text)
        
        result = json.loads(result_text)
        
        # Extract and convert the carbon estimate to a numeric value
        carbon_estimate_str = result.get('carbon_estimate', '')
        carbon_estimate = 0.0
        if 'tons CO2e/year' in carbon_estimate_str:
            carbon_estimate = float(carbon_estimate_str.split(' ')[0])
        
        # Add model version information
        result['model_version'] = "gpt-4"
        result['carbon_estimate'] = carbon_estimate
        
        return result
        
    except Exception as e:
        logger.error("OpenAI analysis error: %s", e)
        # Return fallback values if AI analysis fails
        return {
            "carbon_estimate": estimate_fallback(project_data),
            "confidence_score": 70,
            "methodology": "AI-assisted estimation with standard factors",
            "data_sources": {
                "satellite": "Basic NDVI analysis",
                "standards": "IPCC guidelines",
                "factors": "Conservative estimation factors"
            },
            "risks": ["Limited data points", "Conservative estimate"],
            "recommendations": ["Collect field measurements", "Regular monitoring"],
            "model_version": "fallback"
        }

def estimate_fallback(project_data):
    """
    Provide a basic fallback carbon estimate based on project type and size
    """
    area = float(project_data['area_size'])
    unit_multiplier = 2.47 if project_data['area_unit'] == 'hectares' else 1  # Convert hectares to acres if needed
    area_in_acres = area * unit_multiplier
    
    # Very conservative estimates per acre per year
    rates = {
        'forestry': 3.5,
        'agriculture': 1.2,
        'agroforestry': 2.8,
        'wetland': 4.8,
        'other': 1.0
    }
    
    annual_rate = rates.get(project_data['project_type'], 1.0)
    return round(area_in_acres * annual_rate, 2)

def generate_assessment_report(project_data):
    """
    Generate a detailed assessment report for the project using OpenAI.
    
    Args:
        project_data (dict): Combined project and assessment data
        
    Returns:
        dict: Report generation status and metadata
    """
    try:
        prompt = f"""
        Generate a comprehensive carbon project assessment report with the following information:
        
        Project Name: {project_data['project_name']}
        Project Type: {project_data['project_type']}
        Location: Lat {project_data['location_lat']}, Lng {project_data['location_lng']}
        Area: {project_data['area_size']} {project_data['area_unit']}
        Start Date: {project_data['start_date']}
        
        Assessment Results:
        Carbon Estimate: {project_data['carbon_estimate']} tons CO2e
        Confidence Score: {project_data['confidence_score']}%
        Methodology: {project_data['methodology']}
        
        The report should include:
        1. Executive Summary
        2. Project Description
        3. Assessment Methodology
        4. Results and Carbon Quantification
        5. Verification Procedures
        6. Risk Assessment and Management
        7. Monitoring Plan
        8. Recommendations
        
        This report will be used for carbon credit verification purposes.
        """
        
        logger.info("Sending project data to OpenAI for report generation: %s", project_data)
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a carbon project verification expert. Generate professional, detailed assessment reports following industry standards."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=2500
        )
        
        report_content = response.choices[0].message.content
        logger.info("Received report content from OpenAI: %s", report_content)
        
        # In a production environment, this would generate a PDF
        # Here we're just returning status
        return {
            "status": "generated",
            "format": "pdf",
            "length": len(report_content),
            "project_id": project_data['id']
        }
        
    except Exception as e:
        logger.error("Report generation error: %s", e)
        return {
            "status": "error",
            "message": str(e)
        }