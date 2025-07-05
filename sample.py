from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from pycaret.regression import load_model, predict_model
import uvicorn
import mysql.connector

model = load_model("my_lr_api")
app = FastAPI()
db_config = {
    "host": "localhost",
    "user": "app_user",
    "password": "new_password",
    "database": "insurance_db"
}

def create_table():
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
                   predicted_cost FLOAT
                   )
                """)
    conn.commit()
    cursor.close()
    conn.close()

create_table()

class InsuranceInput(BaseModel):
    age: int
    sex: str
    bmi: float
    children: int
    smoker: str
    region: str

@app.post("/predict")
def predict(data: InsuranceInput):
    input_df = pd.DataFrame([data.model_dump()])
    predictions = predict_model(model, data=input_df)
    predicted_cost = float(predictions["prediction_label"].iloc[0])
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    input_query = """
        INSERT INTO insurance_requests (age, sex, bmi, children, smoker, region, predicted_cost)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""" 
    values = (
        data.age,
        data.sex,
        data.bmi,
        data.children,
        data.smoker,
        data.region,
        predicted_cost
    )
    cursor.execute(input_query, values)
    conn.commit()
    cursor.close()
    conn.close()
    
    return {"Predicted Insurance Cost": predicted_cost}
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)