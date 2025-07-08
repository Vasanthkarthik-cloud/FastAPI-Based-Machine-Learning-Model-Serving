from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
from pycaret.regression import load_model, predict_model
import uvicorn
import mysql.connector
import pika
import json
import threading
import time
from datetime import datetime

app = FastAPI()

# Load model
model = load_model("my_lr_api")

# Database configuration
db_config = {
    "host": "localhost",
    "user": "app_user",
    "password": "new_password",
    "database": "insurance_db"
}

# RabbitMQ configuration
rabbitmq_config = {
    "host": "localhost",
    "port": 5672,
    "username": "guest",
    "password": "guest",
    "queue_name": "insurance_predictions"
}

def create_table():
    """Create database table"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insurance_requests(
            id INT AUTO_INCREMENT PRIMARY KEY,
            age INT,
            sex VARCHAR(10),
            bmi FLOAT,
            children INT,
            smoker VARCHAR(10),
            region VARCHAR(10),
            predicted_cost FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database table created/verified")
    except Exception as e:
        print(f"❌ Database error: {e}")

def test_rabbitmq_connection():
    """Test RabbitMQ connection"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=rabbitmq_config["host"],
                port=rabbitmq_config["port"],
                credentials=pika.PlainCredentials(
                    rabbitmq_config["username"],
                    rabbitmq_config["password"]
                )
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=rabbitmq_config["queue_name"], durable=True)
        connection.close()
        print("✅ RabbitMQ connection successful")
        return True
    except Exception as e:
        print(f"❌ RabbitMQ connection failed: {e}")
        print("Make sure RabbitMQ is running:")
        print("- Docker: docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management")
        print("- Or install locally and start the service")
        return False

def publish_to_rabbitmq(message):
    """Publish message to RabbitMQ"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=rabbitmq_config["host"],
                port=rabbitmq_config["port"],
                credentials=pika.PlainCredentials(
                    rabbitmq_config["username"],
                    rabbitmq_config["password"]
                )
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=rabbitmq_config["queue_name"], durable=True)
        
        channel.basic_publish(
            exchange='',
            routing_key=rabbitmq_config["queue_name"],
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
        print(f"✅ Message published: {message['request_id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to publish message: {e}")
        return False

def save_to_database(data, predicted_cost):
    """Save prediction to database"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        query = """
            INSERT INTO insurance_requests (age, sex, bmi, children, smoker, region, predicted_cost)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        values = (data.age, data.sex, data.bmi, data.children, data.smoker, data.region, predicted_cost)
        cursor.execute(query, values)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Data saved to database")
        return True
    except Exception as e:
        print(f"❌ Database save failed: {e}")
        return False

def process_message(ch, method, properties, body):
    """Process messages from RabbitMQ"""
    try:
        message = json.loads(body)
        print(f"📨 Processing message: {message['request_id']}")
        
        # Create prediction
        data = InsuranceInput(**message['input_data'])
        input_df = pd.DataFrame([data.model_dump()])
        predictions = predict_model(model, data=input_df)
        predicted_cost = float(predictions["prediction_label"].iloc[0])
        
        # Save to database
        save_to_database(data, predicted_cost)
        
        # Acknowledge message
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print(f"✅ Prediction completed: {predicted_cost}")
        
    except Exception as e:
        print(f"❌ Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_consumer():
    """Start RabbitMQ consumer"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=rabbitmq_config["host"],
                port=rabbitmq_config["port"],
                credentials=pika.PlainCredentials(
                    rabbitmq_config["username"],
                    rabbitmq_config["password"]
                )
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=rabbitmq_config["queue_name"], durable=True)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=rabbitmq_config["queue_name"], on_message_callback=process_message)
        
        print("🔄 Starting RabbitMQ consumer...")
        channel.start_consuming()
        
    except Exception as e:
        print(f"❌ Consumer error: {e}")

# Initialize
create_table()
rabbitmq_available = test_rabbitmq_connection()

# Start consumer only if RabbitMQ is available
if rabbitmq_available:
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    print("🚀 RabbitMQ consumer started")
else:
    print("⚠️ RabbitMQ not available - async predictions disabled")

class InsuranceInput(BaseModel):
    age: int
    sex: str
    bmi: float
    children: int
    smoker: str
    region: str

@app.post("/predict")
def predict(data: InsuranceInput):
    """Synchronous prediction"""
    try:
        input_df = pd.DataFrame([data.model_dump()])
        predictions = predict_model(model, data=input_df)
        predicted_cost = float(predictions["prediction_label"].iloc[0])
        
        # Save to database
        save_to_database(data, predicted_cost)
        
        return {"predicted_cost": predicted_cost}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict-async")
def predict_async(data: InsuranceInput):
    """Asynchronous prediction using RabbitMQ"""
    if not rabbitmq_available:
        raise HTTPException(status_code=503, detail="RabbitMQ not available")
    
    try:
        request_id = f"req_{int(datetime.now().timestamp())}"
        message = {
            "input_data": data.model_dump(),
            "request_id": request_id,
            "timestamp": datetime.now().isoformat()
        }
        
        if publish_to_rabbitmq(message):
            return {
                "message": "Prediction queued successfully",
                "request_id": request_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to queue prediction")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "rabbitmq": "available" if rabbitmq_available else "unavailable"
    }

@app.get("/")
def root():
    """Root endpoint with instructions"""
    return {
        "message": "Insurance Prediction API",
        "endpoints": {
            "predict": "POST /predict - Synchronous prediction",
            "predict-async": "POST /predict-async - Asynchronous prediction (requires RabbitMQ)",
            "health": "GET /health - Health check"
        },
        "example_input": {
            "age": 30,
            "sex": "male",
            "bmi": 25.5,
            "children": 2,
            "smoker": "no",
            "region": "northeast"
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)