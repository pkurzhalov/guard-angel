import os
from datetime import datetime
from typing import List, Dict
from pydantic import Field
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
    email_lookup_drivers_raw: str = Field("", alias="EMAIL_LOOKUP_DRIVERS")
    kolobok_dir: str | None = Field(None, alias="KOLOBOK_DIR")
    smtp_user: str = Field(..., alias="SMTP_USER")
    smtp_password: str = Field(..., alias="SMTP_PASSWORD")
    signature_img_path: str = Field(..., alias="SIGNATURE_IMG_PATH")
    geckodriver_path: str = Field(..., alias="GECKODRIVER_PATH")
    firefox_profile_path: str = Field(..., alias="FIREFOX_PROFILE_PATH")
    states_geojson_path: str = Field(..., alias="STATES_GEOJSON_PATH")

    @property
    def owner_operators(self) -> List[str]:
        return [d.strip() for d in self.drivers_owner_operator_raw.split(',') if d.strip()]
    @property
    def company_drivers(self) -> List[str]:
        return [d.strip() for d in self.drivers_company_raw.split(',') if d.strip()]
    @property
    def email_lookup_drivers(self) -> List[str]:
        return [d.strip() for d in self.email_lookup_drivers_raw.split(',') if d.strip()]
    @property
    def authorized_users(self) -> List[int]:
        return [int(x) for x in self.authorized_users_raw.split(',') if x.strip().isdigit()]
    @property
    def invoice_address_block(self) -> str:
        address = self.company_address.replace('\\n', '\n')
        return f"{self.company_name}\n{address}\n{self.company_phone}\n{self.company_email}"
    def get_insurance_pay(self, driver: str) -> int:
        rate = os.getenv(f"INSURANCE_WEEKLY_{driver.upper()}")
        return int(rate) if rate and rate.isdigit() else 0
    def get_trailer_pay(self, driver: str) -> int:
        rate = os.getenv(f"TRAILER_PAYMENT_WEEKLY_{driver.upper()}")
        return int(rate) if rate and rate.isdigit() else 0
    def get_pay_to_name(self, driver: str) -> str:
        return os.getenv(f"PAY_TO_{driver.upper()}", "Driver")

settings = Settings()
