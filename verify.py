from datetime import datetime
import requests
import json

# Function to validate claim based on policy number and loss date with a difference check
def validate_claim(policy_number, loss_date, max_difference_hours=24):
    try:
        print(f"[DEBUG] Starting claim validation for PolicyNumber: {policy_number} and LossDate: {loss_date}")

        # API Endpoint & Headers
        url = "http://18.218.57.115:8090/cc/rest/claimdetails/v1/getClaimDetails"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Basic c3U6Z3c='
        }
        payload = {
            "PolicyNumber": str(policy_number)
        }
        
        print(f"[DEBUG] Sending request to {url} with payload: {payload}")
        
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)

        print(f"[DEBUG] API responded with status code: {response.status_code}")

        if response.status_code != 200:
            print(f"[ERROR] API request failed with status {response.status_code}: {response.text}")
            return None

        try:
            claim_data = response.json()
            print(f"[DEBUG] Parsed JSON response successfully.")
        except json.JSONDecodeError:
            print("[ERROR] Failed to parse JSON response.")
            return None

        if not isinstance(claim_data, list):
            print("[ERROR] Unexpected response format: expected a list of claims.")
            return None

        print(f"[DEBUG] Number of claims received: {len(claim_data)}")

        # Convert input loss_date to datetime for comparison
        input_loss_date_obj = datetime.fromisoformat(loss_date.replace("Z", "+00:00"))

        # Process claims to find the latest one matching the loss date within the threshold
        latest_claim = None
        latest_create_date = None

        for claim in claim_data:
            print(f"[DEBUG] Checking claim {claim.get('ClaimNumber')}")
            
            claim_loss_date_str = claim.get("LossDate")
            if not claim_loss_date_str:
                print("[DEBUG] Claim has no LossDate.")
                continue
            
            claim_loss_date_obj = datetime.fromisoformat(claim_loss_date_str.replace("Z", "+00:00"))
            difference = abs((claim_loss_date_obj - input_loss_date_obj).total_seconds()) / 3600  # Difference in hours
            
            print(f"[DEBUG] LossDate difference in hours: {difference:.2f}")

            if difference < max_difference_hours:
                print(f"[DEBUG] LossDate within {max_difference_hours} hours: {claim_loss_date_str}")
                create_dates = [exposure.get("CreateDate") for exposure in claim.get("Exposures", []) if exposure.get("CreateDate")]
                print(f"[DEBUG] Found {len(create_dates)} create dates in exposures.")
                
                for date_str in create_dates:
                    print(f"[DEBUG] Parsing CreateDate: {date_str}")
                    date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if latest_create_date is None or date_obj > latest_create_date:
                        print(f"[DEBUG] Updating latest create date to {date_obj}")
                        latest_create_date = date_obj
                        latest_claim = {
                            "LossDate": claim_loss_date_str,
                            "ClaimNumber": claim.get("ClaimNumber"),
                            "CreateDate": date_str,
                            "PolicyType": claim.get("PolicyType"),
                            "ClaimStatus": claim.get("ClaimStatus"),
                            "PolicyNumber": claim.get("PolicyNumber"),
                            "Status": "Duplicate",
                            "LossDateDifferenceHours": round(difference, 2)
                        }
            else:
                print(f"[DEBUG] LossDate difference too large: {claim_loss_date_str}")

        if not latest_claim:
            print("[DEBUG] No matching claims found.")
            return None
        
        print(f"[DEBUG] Latest matching claim found: {latest_claim}")
        return latest_claim

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API request exception occurred: {e}")
        return None

# Function to call AI service to verifuy duplicate claims
def validate_Duplicate_Claim(policy_number, cleaned_text):
    """
    Calls the Get Claim Details API.
    - If the API clearly says no claims exist, returns None immediately.
    - Otherwise, sends the data to AI for a deeper check.
    - Returns dict with policyNumber, claimNumber, lossDate, and status='found' if found, else None.
    """
    try:
        #print("\n[DEBUG] Starting duplicate claim validation...")
        #print(f"[DEBUG] Input Policy Number: {policy_number}")
        #print(f"[DEBUG] Cleaned Text (truncated): {cleaned_text[:200]}...")  # Avoid printing huge text

        # 1️⃣ API Endpoint & Headers
        url = "http://18.218.57.115:8090/cc/rest/claimdetails/v1/getClaimDetails"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Basic c3U6Z3c='
        }
        payload = {
            "PolicyNumber": str(policy_number)
        }
     

        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if response.status_code != 200:
           # print(f"[ERROR] Get Claim API failed: {response.status_code} - {response.text}")
            return None

        try:
            claim_data = response.json()
           
        except Exception as e:
            
            return None

        # 2️⃣ Quick check before AI
        if not claim_data or "no claim" in json.dumps(claim_data).lower():
            print("[DEBUG] No claim data found in API response. Returning None.")
            return None

        # 3️⃣ Build AI prompt
        prompt = f"""
You are an professional claim validator. 
You must strictly follow the instructions.

Claim data from the API:
{claim_data}

User request text:
{cleaned_text}

### Your Task:
1. Extract the **Loss Date** from {cleaned_text} and lets name as "RequestLossDate"   

   RequestLossDate =  Loss Date: normalize it to this format → YYYY-MM-DDTHH:MM:SS-07:00  
     (example: 2025-07-14T15:30:00-07:00). If time is missing, assume 00:00:00.  

2. Here is the List of previous claim data {claim_data}. I want you to go through it thoroughly,verify if the 
claim data has a claim details having "lossDate" = RequestLossDate. If found,
extract the details of the latest claim as follows, return ONLY this JSON:  
  
    {{
       "policyNumber": "<policyNumber from API>",
       "claimNumber": "<claimNumber from API>",
       "lossDate": "<lossDate from API>",
       "claimStatus": "<claimStatus from API>",
       "status": "duplicate"
   }}
3. Do not mark the status as duplicate if the loss Date is different.
4. If Duplicate Claim is not found then return ONLY this JSON:  
   {{
       "status": "new"
   }}

### Rules:

- Do not explain your reasoning.  
- Do not output anything other than the JSON.  
"""


        # 4️⃣ Call AI
       
        ai_result = get_ai_content(prompt)
        print("AI Result:", ai_result)

        # 🛠 Clean AI output before parsing
        try:
            import re
            cleaned_ai_result = re.sub(r"^```[a-zA-Z]*\s*|```$", "", ai_result.strip(), flags=re.MULTILINE).strip()
            # print(f"[DEBUG] Cleaned AI Result: {cleaned_ai_result}")
            result_json = json.loads(cleaned_ai_result)
            # print(f"[DEBUG] Parsed AI JSON: {result_json}")
        except Exception as e:
            #print(f"[ERROR] Failed to parse AI output as JSON after cleaning: {e}")
            result_json = None

        return result_json

    except Exception as e:
        #print(f"[ERROR] Exception in validate_Duplicate_Claim: {e}")
        return None



