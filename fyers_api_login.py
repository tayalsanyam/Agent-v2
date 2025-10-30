#!/usr/bin/env python3
"""
Fyers API-Based Login Script
Uses direct API calls instead of Selenium
Based on Fyers API v3 documentation
"""

import json
import sys
import time
import os
import requests
import pyotp
from urllib.parse import parse_qs, urlparse
from fyers_apiv3 import fyersModel
import configparser
from datetime import datetime

# Constants
SUCCESS = 1
ERROR = -1

class FyersAPILogin:
    def __init__(self):
        """Initialize with your credentials"""
        # App credentials
        self.APP_ID = "GFMT974FFL"  # Without the -100 suffix
        self.APP_TYPE = "100"  # The suffix part
        self.SECRET_KEY = "G3ZTX7DL5A"
        self.client_id = f"{self.APP_ID}-{self.APP_TYPE}"  # GFMT974FFL-100
        
        # User credentials
        self.FY_ID = "YS58421"  # Your Fyers ID
        self.APP_ID_TYPE = "2"  # 2 denotes web login
        self.TOTP_KEY = "W3KXXB46D7WISIPBHPP7HDGYWIH7NBLI"
        self.PIN = "2524"
        self.REDIRECT_URI = "https://www.google.com"  # Your redirect URI
        
        # API endpoints
        self.BASE_URL = "https://api-t2.fyers.in/vagator/v2"
        self.BASE_URL_2 = "https://api-t1.fyers.in/api/v3"
        self.URL_SEND_LOGIN_OTP = self.BASE_URL + "/send_login_otp"
        self.URL_VERIFY_TOTP = self.BASE_URL + "/verify_otp"
        self.URL_VERIFY_PIN = self.BASE_URL + "/verify_pin"
        self.URL_TOKEN = self.BASE_URL_2 + "/token"
        self.URL_VALIDATE_AUTH_CODE = self.BASE_URL_2 + "/validate-authcode"
        
        # Token storage
        self.access_token = None
        self.auth_code = None

    def send_login_otp(self):
        """Step 1: Send login OTP request"""
        try:
            print("[INFO] Sending login OTP request...")
            result_string = requests.post(
                url=self.URL_SEND_LOGIN_OTP, 
                json={
                    "fy_id": self.FY_ID, 
                    "app_id": self.APP_ID_TYPE
                }
            )
            
            if result_string.status_code != 200:
                return [ERROR, result_string.text]
            
            result = json.loads(result_string.text)
            request_key = result["request_key"]
            print("[OK] Login OTP request successful")
            return [SUCCESS, request_key]
            
        except Exception as e:
            print(f"[ERROR] Send login OTP failed: {e}")
            return [ERROR, e]

    def generate_totp(self):
        """Step 2: Generate TOTP"""
        try:
            print("[INFO] Generating TOTP...")
            generated_totp = pyotp.TOTP(self.TOTP_KEY).now()
            print(f"[OK] TOTP generated: {generated_totp}")
            return [SUCCESS, generated_totp]
        except Exception as e:
            print(f"[ERROR] TOTP generation failed: {e}")
            return [ERROR, e]

    def verify_totp(self, request_key, totp):
        """Step 3: Verify TOTP and get new request key"""
        try:
            print(f"[INFO] Verifying TOTP...")
            print(f"[DEBUG] TOTP: {totp}, Request Key: {request_key[:20]}...")
            
            result_string = requests.post(
                url=self.URL_VERIFY_TOTP, 
                json={
                    "request_key": request_key, 
                    "otp": totp
                }
            )
            
            if result_string.status_code != 200:
                return [ERROR, result_string.text]
            
            result = json.loads(result_string.text)
            new_request_key = result["request_key"]
            print("[OK] TOTP verified successfully")
            return [SUCCESS, new_request_key]
            
        except Exception as e:
            print(f"[ERROR] TOTP verification failed: {e}")
            return [ERROR, e]

    def verify_pin(self, request_key):
        """Step 4: Verify PIN and get access token"""
        try:
            print("[INFO] Verifying PIN...")
            payload = {
                "request_key": request_key,
                "identity_type": "pin",
                "identifier": self.PIN
            }
            
            result_string = requests.post(
                url=self.URL_VERIFY_PIN, 
                json=payload
            )
            
            if result_string.status_code != 200:
                return [ERROR, result_string.text]
            
            result = json.loads(result_string.text)
            access_token = result["data"]["access_token"]
            print("[OK] PIN verified successfully")
            return [SUCCESS, access_token]
            
        except Exception as e:
            print(f"[ERROR] PIN verification failed: {e}")
            return [ERROR, e]

    def get_auth_code(self, access_token):
        """Step 5: Get auth code for API V2 App"""
        try:
            print("[INFO] Getting auth code...")
            payload = {
                "fyers_id": self.FY_ID,
                "app_id": self.APP_ID,
                "redirect_uri": self.REDIRECT_URI,
                "appType": self.APP_TYPE,
                "code_challenge": "",
                "state": "sample_state",
                "scope": "",
                "nonce": "",
                "response_type": "code",
                "create_cookie": True
            }
            
            headers = {'Authorization': f'Bearer {access_token}'}
            
            result_string = requests.post(
                url=self.URL_TOKEN, 
                json=payload, 
                headers=headers
            )
            
            if result_string.status_code != 308:
                return [ERROR, result_string.text]
            
            result = json.loads(result_string.text)
            url = result["Url"]
            auth_code = parse_qs(urlparse(url).query)['auth_code'][0]
            print(f"[OK] Auth code obtained: {auth_code[:20]}...")
            return [SUCCESS, auth_code]
            
        except Exception as e:
            print(f"[ERROR] Auth code retrieval failed: {e}")
            return [ERROR, e]

    def generate_access_token(self, auth_code):
        """Step 6: Generate final access token"""
        try:
            print("[INFO] Generating final access token...")
            session = fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.SECRET_KEY,
                redirect_uri=self.REDIRECT_URI,
                response_type='code',
                grant_type='authorization_code'
            )
            
            session.set_token(auth_code)
            response = session.generate_token()
            
            if response.get('s') == 'ERROR':
                print("[ERROR] Cannot generate token. Check credentials!")
                return None
            
            access_token = response["access_token"]
            print("[OK] Access token generated successfully")
            return access_token
            
        except Exception as e:
            print(f"[ERROR] Access token generation failed: {e}")
            return None

    def save_tokens(self, access_token, auth_code):
        """Save tokens to configuration files"""
        print("\n[INFO] Saving tokens to configuration files...")
        
        # Save to config_fyers.ini (matching fyersauth.py format)
        config = configparser.ConfigParser()
        config_file = 'config_fyers.ini'
        
        # Read existing config if it exists
        if os.path.exists(config_file):
            config.read(config_file)
        
        if 'FYERS' not in config:
            config['FYERS'] = {}
        
        # Save exactly as fyersauth.py does
        config['FYERS']['client_id'] = self.client_id
        config['FYERS']['secret_key'] = self.SECRET_KEY
        config['FYERS']['redirect_uri'] = self.REDIRECT_URI
        config['FYERS']['auth_code'] = auth_code
        config['FYERS']['access_token'] = access_token
        
        with open(config_file, 'w') as f:
            config.write(f)
        print(f"[OK] Saved to {config_file}")
        
        # Save to config.json (matching fyersauth.py format)
        json_config = {}
        
        # Read existing JSON if it exists
        if os.path.exists('config.json'):
            try:
                with open('config.json', 'r') as f:
                    json_config = json.load(f)
            except:
                pass
        
        # Update with exact same fields as fyersauth.py
        json_config.update({
            'client_id': self.client_id,
            'access_token': access_token,
            # Store additional info for reference (as per fyersauth.py)
            'secret_key': self.SECRET_KEY,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_timestamp': int(time.time())
        })
        
        with open('config.json', 'w') as f:
            json.dump(json_config, f, indent=4)
        print("[OK] Saved to config.json")
        
        # Save access token to access.txt
        with open('access.txt', 'w') as f:
            f.write(access_token)
        print("[OK] Saved to access.txt")

    def verify_connection(self, access_token):
        """Verify the access token works"""
        try:
            print("\n[INFO] Verifying connection...")
            fyers = fyersModel.FyersModel(
                token=access_token,
                is_async=False,
                client_id=self.client_id,
                log_path=""
            )
            
            profile = fyers.get_profile()
            if profile and profile.get('code') == 200:
                user_data = profile.get('data', {})
                print(f"[OK] Connected as: {user_data.get('display_name', 'N/A')} ({user_data.get('fy_id', 'N/A')})")
                
                # Try to get funds
                try:
                    funds = fyers.funds()
                    if funds and funds.get('code') == 200:
                        fund_data = funds.get('fund_limit', [])
                        if fund_data:
                            balance = fund_data[0].get('equityAmount', 0)
                            print(f"[OK] Available Balance: Rs.{balance:,.2f}")
                except:
                    pass
                
                return True
            else:
                print("[WARNING] Could not verify connection")
                return False
                
        except Exception as e:
            print(f"[WARNING] Connection verification failed: {e}")
            return False

    def run(self):
        """Main execution flow"""
        print("=" * 60)
        print("FYERS API-BASED LOGIN")
        print("=" * 60)
        print(f"Client ID: {self.client_id}")
        print(f"Fyers ID: {self.FY_ID}")
        print(f"Redirect URI: {self.REDIRECT_URI}")
        print("=" * 60)
        
        # Step 1: Generate auth URL (for reference)
        session = fyersModel.SessionModel(
            client_id=self.client_id,
            secret_key=self.SECRET_KEY,
            redirect_uri=self.REDIRECT_URI,
            response_type='code',
            grant_type='authorization_code'
        )
        
        url_to_activate = session.generate_authcode()
        print(f"\n[INFO] Auth URL (for manual activation if needed):")
        print(f"  {url_to_activate}\n")
        
        # Step 2: Send login OTP
        send_otp_result = self.send_login_otp()
        if send_otp_result[0] != SUCCESS:
            print(f"[ERROR] Send login OTP failed: {send_otp_result[1]}")
            return False
        
        request_key = send_otp_result[1]
        
        # Step 3: Generate TOTP
        generate_totp_result = self.generate_totp()
        if generate_totp_result[0] != SUCCESS:
            print(f"[ERROR] Generate TOTP failed: {generate_totp_result[1]}")
            return False
        
        totp = generate_totp_result[1]
        
        # Step 4: Verify TOTP (with retry)
        verify_totp_result = None
        for attempt in range(1, 4):
            print(f"\n[INFO] TOTP verification attempt {attempt}/3")
            verify_totp_result = self.verify_totp(request_key, totp)
            
            if verify_totp_result[0] == SUCCESS:
                break
            else:
                print(f"[WARNING] TOTP verification failed: {verify_totp_result[1]}")
                if attempt < 3:
                    time.sleep(2)
                    # Generate new TOTP for retry
                    generate_totp_result = self.generate_totp()
                    if generate_totp_result[0] == SUCCESS:
                        totp = generate_totp_result[1]
        
        if verify_totp_result[0] != SUCCESS:
            print("[ERROR] All TOTP verification attempts failed")
            return False
        
        request_key_2 = verify_totp_result[1]
        
        # Step 5: Verify PIN
        verify_pin_result = self.verify_pin(request_key_2)
        if verify_pin_result[0] != SUCCESS:
            print(f"[ERROR] PIN verification failed: {verify_pin_result[1]}")
            return False
        
        trade_access_token = verify_pin_result[1]
        
        # Step 6: Get auth code
        token_result = self.get_auth_code(trade_access_token)
        if token_result[0] != SUCCESS:
            print(f"[ERROR] Auth code retrieval failed: {token_result[1]}")
            return False
        
        auth_code = token_result[1]
        
        # Step 7: Generate final access token
        final_access_token = self.generate_access_token(auth_code)
        if not final_access_token:
            print("[ERROR] Final access token generation failed")
            return False
        
        print(f"\n[SUCCESS] Access Token: {final_access_token[:50]}...")
        
        # Save tokens
        self.save_tokens(final_access_token, auth_code)
        
        # Verify connection
        self.verify_connection(final_access_token)
        
        print("\n" + "=" * 60)
        print("[SUCCESS] Login completed successfully!")
        print("Files created/updated:")
        print("  - config_fyers.ini")
        print("  - config.json")
        print("  - access.txt")
        print("=" * 60)
        
        return True


def main():
    """Main entry point"""
    # Check for required packages
    required_packages = ['fyers-apiv3', 'requests', 'pyotp']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"[ERROR] Missing required packages: {', '.join(missing_packages)}")
        print(f"Install with: pip install {' '.join(missing_packages)}")
        sys.exit(1)
    
    # Run the login process
    login = FyersAPILogin()
    success = login.run()
    
    if not success:
        print("\n[ERROR] Login failed!")
        print("\nTroubleshooting tips:")
        print("1. Verify your Fyers ID (YS58421) is correct")
        print("2. Check your TOTP key is correct")
        print("3. Verify your PIN (2524) is correct")
        print("4. Ensure your app credentials are valid")
        print("5. Check if 2FA TOTP is enabled in your Fyers account")
        sys.exit(1)


if __name__ == "__main__":
    main()