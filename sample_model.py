import pandas as pd
from pycaret.regression import setup, compare_models, save_model

df=pd.read_csv("https://raw.githubusercontent.com/stedy/Machine-Learning-with-R-datasets/master/insurance.csv")
df.columns=["age", "sex", "bmi", "children", "smoker", "region", "charges"]
reg=setup(df, target="charges", session_id=123)
best_model=compare_models()
save_model(best_model, "my_lr_api")
