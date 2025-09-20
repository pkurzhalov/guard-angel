from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

from dotenv import find_dotenv
# Force-load project .env with override=True
load_dotenv(find_dotenv(usecwd=True), override=True)

class Settings(BaseSettings):
    # Telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")
    authorized_users_raw: str = Field("", alias="AUTHORIZED_USERS")  # <-- keep as string

    # Google
    spreadsheet_id: str = Field(..., alias="SPREADSHEET_ID")
    drive_folder_statements: str = Field(..., alias="DRIVE_FOLDER_STATEMENTS")

    # Salary logic
    trailer_payment: int = Field(500, alias="TRAILER_PAYMENT")
    insurance_cutoff: str = Field("06/30/2023", alias="INSURANCE_CUTOFF")

    # Start rows
    cell_yura: int = Field(205, alias="CELL_YURA")
    cell_walter: int = Field(534, alias="CELL_WALTER")
    cell_denis: int = Field(63, alias="CELL_DENIS")
    cell_test: int = Field(28, alias="CELL_TEST")
    cell_javier: int = Field(9, alias="CELL_JAVIER")
    cell_nestor: int = Field(67, alias="CELL_NESTOR")

    # helpers
    @property
    def authorized_users(self) -> List[int]:
        return [int(x) for x in self.authorized_users_raw.split(",") if x.strip().isdigit()]

    def get_start_row(self, driver: str) -> int:
        return {
            "Yura": self.cell_yura,
            "Walter": self.cell_walter,
            "Denis": self.cell_denis,
            "Javier": self.cell_javier,
            "Nestor": self.cell_nestor,
        }.get(driver, self.cell_test)

    def get_insurance_pay(self, driver: str, date: datetime) -> int:
        cutoff = datetime.strptime(self.insurance_cutoff, "%m/%d/%Y")
        if date <= cutoff:
            return 292
        if driver in ("Nestor", "Javier", "Walter"):
            return 292
        raise ValueError(f"Unknown driver for insurance: {driver}")

settings = Settings()
