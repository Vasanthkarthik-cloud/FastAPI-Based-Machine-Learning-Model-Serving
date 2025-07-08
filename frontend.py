import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# Page configuration
st.set_page_config(
    page_title="Insurance Cost Predictor",
    page_icon="🏥",
    layout="wide"
)

# API Configuration
API_BASE_URL = "http://127.0.0.1:8000"

# Initialize session state
if 'prediction_history' not in st.session_state:
    st.session_state.prediction_history = []

if 'api_status' not in st.session_state:
    st.session_state.api_status = None

def check_api_health():
    """Check API health status"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except:
        return None

def make_prediction(data, async_mode=False):
    """Make prediction API call"""
    try:
        endpoint = "/predict-async" if async_mode else "/predict"
        response = requests.post(
            f"{API_BASE_URL}{endpoint}",
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json(), None
        else:
            return None, f"API Error: {response.status_code} - {response.text}"
    except requests.exceptions.Timeout:
        return None, "Request timed out. Please try again."
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to API. Make sure the server is running."
    except Exception as e:
        return None, f"Error: {str(e)}"

def create_comparison_chart(history):
    """Create a comparison chart of predictions"""
    if not history:
        return None
    
    df = pd.DataFrame(history)
    
    fig = px.scatter(
        df, 
        x='age', 
        y='predicted_cost',
        size='bmi',
        color='smoker',
        hover_data=['sex', 'children', 'region'],
        title="Insurance Cost Predictions Overview"
    )
    
    return fig

def create_factor_analysis(age, bmi, children, smoker):
    """Create factor analysis visualization"""
    factors = {
        'Age Impact': min(age * 100, 2000),
        'BMI Impact': max(0, (bmi - 18.5) * 200),
        'Children Impact': children * 300,
        'Smoking Impact': 10000 if smoker == 'yes' else 0
    }
    
    fig = go.Figure(data=[
        go.Bar(
            x=list(factors.keys()),
            y=list(factors.values())
        )
    ])
    
    fig.update_layout(
        title="Cost Factor Analysis",
        xaxis_title="Factors",
        yaxis_title="Estimated Impact ($)"
    )
    
    return fig

# Main app
def main():
    st.title("Insurance Cost Predictor")
    
    # Check API status
    with st.spinner("Checking API status..."):
        health_status = check_api_health()
        
    if health_status:
        st.session_state.api_status = health_status
        st.success(f"API is healthy - RabbitMQ: {health_status.get('rabbitmq', 'unknown')}")
    else:
        st.error("API is not available. Please make sure your FastAPI server is running on http://127.0.0.1:8000")
        st.stop()
    
    # Sidebar for input
    st.sidebar.header("Input Parameters")
    
    # Input fields
    age = st.sidebar.number_input(
        "Age",
        min_value=18,
        max_value=100,
        value=30
    )
    
    sex = st.sidebar.selectbox(
        "Sex",
        options=["male", "female"]
    )
    
    bmi = st.sidebar.number_input(
        "BMI",
        min_value=10.0,
        max_value=50.0,
        value=25.0,
        step=0.1
    )
    
    children = st.sidebar.number_input(
        "Children",
        min_value=0,
        max_value=10,
        value=0
    )
    
    smoker = st.sidebar.selectbox(
        "Smoker",
        options=["no", "yes"]
    )
    
    region = st.sidebar.selectbox(
        "Region",
        options=["northeast", "northwest", "southeast", "southwest"]
    )
    
    # Prediction buttons
    st.sidebar.markdown("---")
    st.sidebar.header("Make Prediction")
    
    sync_button = st.sidebar.button("Predict Now (Sync)")
    
    # Only show async button if RabbitMQ is available
    async_available = st.session_state.api_status.get('rabbitmq') == 'available'
    if async_available:
        async_button = st.sidebar.button("Queue Prediction (Async)")
    else:
        st.sidebar.info("Async predictions require RabbitMQ")
        async_button = False
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Prediction Results")
        
        # Prepare input data
        input_data = {
            "age": age,
            "sex": sex,
            "bmi": bmi,
            "children": children,
            "smoker": smoker,
            "region": region
        }
        
        # Handle sync prediction
        if sync_button:
            with st.spinner("Making prediction..."):
                result, error = make_prediction(input_data, async_mode=False)
                
                if result:
                    predicted_cost = result["predicted_cost"]
                    
                    # Display result
                    st.success(f"💰 Predicted Insurance Cost: ${predicted_cost:,.2f}")
                    
                    # Add to history
                    prediction_record = input_data.copy()
                    prediction_record['predicted_cost'] = predicted_cost
                    prediction_record['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.prediction_history.append(prediction_record)
                    
                    # Show factor analysis
                    st.subheader("Cost Factor Analysis")
                    factor_chart = create_factor_analysis(age, bmi, children, smoker)
                    st.plotly_chart(factor_chart, use_container_width=True)
                    
                else:
                    st.error(f"Prediction failed: {error}")
        
        # Handle async prediction
        if async_button:
            with st.spinner("Queuing prediction..."):
                result, error = make_prediction(input_data, async_mode=True)
                
                if result:
                    st.success(f"Prediction queued successfully!")
                    st.info(f"Request ID: {result['request_id']}")
                    st.info("Your prediction is being processed in the background. Check your database for results.")
                else:
                    st.error(f"Failed to queue prediction: {error}")
    
    with col2:
        st.header("Insights")
        
        # BMI Category
        if bmi < 18.5:
            bmi_category = "Underweight"
        elif bmi < 25:
            bmi_category = "Normal"
        elif bmi < 30:
            bmi_category = "Overweight"
        else:
            bmi_category = "Obese"
        
        st.metric("BMI Category", bmi_category, f"BMI: {bmi:.1f}")
        
        # Risk Factors
        risk_factors = []
        if smoker == "yes":
            risk_factors.append("🚬 Smoking")
        if bmi > 30:
            risk_factors.append("⚖️ High BMI")
        if age > 50:
            risk_factors.append("👴 Age > 50")
        
        if risk_factors:
            st.subheader("Risk Factors")
            for factor in risk_factors:
                st.write(f"- {factor}")
        else:
            st.success("No major risk factors")
    
    # Prediction History
    if st.session_state.prediction_history:
        st.markdown("---")
        st.header("Prediction History")
        
        # Display history table
        history_df = pd.DataFrame(st.session_state.prediction_history)
        st.dataframe(history_df, use_container_width=True)
        
        # Visualization
        if len(st.session_state.prediction_history) > 1:
            st.subheader("Predictions Comparison")
            comparison_chart = create_comparison_chart(st.session_state.prediction_history)
            if comparison_chart:
                st.plotly_chart(comparison_chart, use_container_width=True)
        
        # Clear history button
        if st.button("Clear History"):
            st.session_state.prediction_history = []
            st.rerun()
    
    # Footer
    st.markdown("---")
    st.info("💡 This tool predicts insurance costs based on personal factors")

if __name__ == "__main__":
    main()