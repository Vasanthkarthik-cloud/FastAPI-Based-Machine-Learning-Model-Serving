from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from pycaret.regression import load_model, predict_model
import uvicorn

model=load_model("my_lr_api")
app=FastAPI()

class InsuranceInput(BaseModel):
    age: int
    sex: str
    bmi: float
    children: int
    smoker: str
    region: str

@app.post("/predict")
def predict(data: InsuranceInput):
    input_df=pd.DataFrame([data.model_dump()])
    predictions=predict_model(model, data=input_df)
    
    return {"Predicted Insuarance Cost": float(predictions["prediction_label"].iloc[0])}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)