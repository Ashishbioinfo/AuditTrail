# AbhiLekh

Streamlit flag-review and authority-validation portal for illustrative urban-change screening cases.

## Run locally

Requires Python 3.11 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

For Streamlit Community Cloud, connect the GitHub repository and select `streamlit_app.py` as the app's main file. Anomaly results can be exported from the Construction Watch detector and imported into the analyst queue. See [SETUP.md](SETUP.md) for the handoff and authority evidence workflow.
