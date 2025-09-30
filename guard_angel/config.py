import os
from datetime import datetime
from typing import List, Dict
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    
    bot_token: str = Field(..., alias="BOT_TOKEN")
    authorized_users_raw: str = Field(..., alias="AUTHORIZED_USERS")
    spreadsheet_id: str = Field(..., alias="SPREADSHEET_ID")
    drive_folder_id: str = Field(..., alias="DRIVE_FOLDER_ID")
    company_name: str = Field(..., alias="COMPANY_NAME")
    company_address: str = Field(..., alias="COMPANY_ADDRESS")
    company_phone: str = Field(..., alias="COMPANY_PHONE")
    company_email: str = Field(..., alias="COMPANY_EMAIL")
    company_payee_name: str = Field(..., alias="COMPANY_PAYEE_NAME")
    company_bank_name: str = Field(..., alias="COMPANY_BANK_NAME")
    company_bank_phone: str = Field(..., alias="COMPANY_BANK_PHONE")
    company_routing_number: str = Field(..., alias="COMPANY_ROUTING_NUMBER")
    company_account_number: str = Field(..., alias="COMPANY_ACCOUNT_NUMBER")
    drivers_owner_operator_raw: str = Field("", alias="DRIVERS_OWNER_OPERATOR")
    drivers_company_raw: str = Field("", alias="DRIVERS_COMPANY")
    kolobok_dir: str | None = Field(None, alias="KOLOBOK_DIR")
    smtp_user: str = Field(..., alias="SMTP_USER")
    smtp_password: str = Field(..., alias="SMTP_PASSWORD")
    signature_img_path: str = Field(..., alias="SIGNATURE_IMG_PATH")
    
    signature_coords_x: int = Field(50, alias="SIGNATURE_COORDS_X")
    signature_coords_y: int = Field(80, alias="SIGNATURE_COORDS_Y")
    signature_scale: float = Field(0.3, alias="SIGNATURE_SCALE")
    date_coords_x: int = Field(200, alias="DATE_COORDS_X")
    date_coords_y: int = Field(95, alias="DATE_COORDS_Y")
    custom_text_coords_x: int = Field(300, alias="CUSTOM_TEXT_COORDS_X")
    custom_text_coords_y: int = Field(95, alias="CUSTOM_TEXT_COORDS_Y")

    owner_operators: List[str] = []; company_drivers: List[str] = []
    insurance_rates: Dict[str, int] = {}; trailer_rates: Dict[str, int] = {}
    pay_to_map: Dict[str, str] = {}; invoice_address_block: str = ""

    @model_validator(mode='after')
    def process_dynamic_data(self) -> 'Settings':
        self.owner_operators = [d.strip() for d in self.drivers_owner_operator_raw.split(',') if d.strip()]
        self.company_drivers = [d.strip() for d in self.drivers_company_raw.split(',') if d.strip()]
        all_drivers = self.owner_operators + self.company_drivers
        for driver in all_drivers:
            if driver in self.owner_operators:
                ins_rate = os.getenv(f"INSURANCE_WEEKLY_{driver.upper()}"); trl_rate = os.getenv(f"TRAILER_PAYMENT_WEEKLY_{driver.upper()}")
                if ins_rate and ins_rate.isdigit(): self.insurance_rates[driver] = int(ins_rate)
                if trl_rate and trl_rate.isdigit(): self.trailer_rates[driver] = int(trl_rate)
            payee = os.getenv(f"PAY_TO_{driver.upper()}"); 
            if payee: self.pay_to_map[driver] = payee
        address = self.company_address.replace('\\n', '\n')
        self.invoice_address_block = (f"{self.company_name}\n{address}\n{self.company_phone}\n{self.company_email}")
        return self

    @property
    def authorized_users(self) -> List[int]:
        return [int(x) for x in self.authorized_users_raw.split(',') if x.strip().isdigit()]
    def get_insurance_pay(self, driver: str) -> int: return self.insurance_rates.get(driver, 0)
    def get_trailer_pay(self, driver: str) -> int: return self.trailer_rates.get(driver, 0)

settings = Settings()
