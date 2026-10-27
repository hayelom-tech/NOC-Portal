"""HTTP routes for the legacy domain."""
from fastapi import Depends
from fastapi import APIRouter
from server.services.security import get_current_user
from fastapi import APIRouter
from server.services.static_data import read_csv

router = APIRouter()

@router.get("/api/data")
def api_data(user=Depends(get_current_user)):
    return {
        "networkKPIs": read_csv("kpi_data.csv"),
        "nocMatrix": read_csv("matrix_data.csv"),
        "regions": read_csv("regional_data.csv"),
        "chronic": read_csv("chronic_data.csv"),
    }


@router.get("/api/roster")
def api_roster(user=Depends(get_current_user)):
    return {"roster": read_csv("roster.csv")}


@router.get("/api/oncall")
def api_oncall(user=Depends(get_current_user)):
    return {"oncall": read_csv("oncall.csv")}


@router.get("/api/process-docs")
def api_process_docs(user=Depends(get_current_user)):
    return {"docs": read_csv("process_docs.csv")}
