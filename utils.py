from logging import root
from model import get_ai_content
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import json


def get_email_intent(body):

    prompt = f"""
You are an insurance claim email classification assistant.
You will be given the body of an email. Your task is to determine the intent **only if the email is from the customer** in response to a claim-related communication.

## Classification Rules:
1. Ignore and return "SystemMessage" if the email is clearly from the company/system 
   (e.g., claim registration confirmation, automated status updates, disclaimers) and not from the customer.
2. If the email is from the customer:
   - Return "Proceed" if the customer is explicitly asking to move forward with the claim process 
     or confirming they want it processed.
       Examples: "Please proceed", "Yes, go ahead", "I want to file this claim", 
       "Continue with the process", "Proceed with my claim", "Please start the process".
   - Return "Acknowledge" if the customer is simply thanking, acknowledging receipt, 
     or expressing appreciation without requesting further action.
       Examples: "Thank you", "Got it", "I appreciate your help", "Noted", "Thanks for letting me know".

## Few-Shot Examples:
Email: "Please proceed with my claim, I agree with your assessment."
Output: "Proceed"

Email: "Thanks for letting me know about the duplicate claim."
Output: "Acknowledge"

Email: "I understand there might be a duplicate, but I want to go ahead with the claim."
Output: "Proceed"

Email: "Claim Number: 000-00-004665 has been successfully registered."
Output: "SystemMessage"

Email: "I appreciate your quick response."
Output: "Acknowledge"

Email: "Yes, go ahead and file it."
Output: "Proceed"

## Output format:
Return only one of these strings exactly:
- "SystemMessage"
- "Proceed"
- "Acknowledge"

## Email Body:
{body}
"""
    
    response = get_ai_content(prompt)
    print("Intent Response:", response)  
    return response.strip()


# Method to parse and verify if the policy is inforce or expired
def verify_policy_details(policy_details):
    try:
       
        if policy_details.strip().startswith("["):
            xml_list = json.loads(policy_details)
            xml_string = xml_list[0]
        else:
            xml_string = policy_details

       
        ns = {'ns': 'http://guidewire.com/pc/gx/gw.webservice.pc.pc1000.gxmodel.policyperiodmodel'}

       
        root = ET.fromstring(xml_string)
        
       
        period_end = root.find('ns:PeriodEnd', ns)
        if period_end is not None:
            period_end_dt = datetime.fromisoformat(period_end.text.replace("Z", "+00:00"))
            
        else:
            
            return None, None, None, None

        # Extract Effective Date
        effective_date = root.find('ns:Policy/ns:OriginalEffectiveDate', ns)
        if effective_date is not None:
            effective_date_dt = datetime.fromisoformat(effective_date.text.replace("Z", "+00:00"))
        else:
            effective_date_dt = None

        # Extract Policy Type
        policy_type = None
        for elem in root.iter():
            if elem.tag.endswith("PolicyType"):
                policy_type = elem.text
                break

        # Extract Policy Number
        policy_number = root.find('ns:PolicyNumber', ns)
        policy_number = policy_number.text if policy_number is not None else None

        # Today's date (UTC)
        today = datetime.now(timezone.utc)
        status = "Expired" if today > period_end_dt else "Inforce"

        return status, policy_type

    except Exception as e:
        return None, None

def verify_policy(policy_details, loss_date_str):
    try:
        
        if policy_details.strip().startswith("["):
            xml_list = json.loads(policy_details)
            xml_string = xml_list[0]
        else:
            xml_string = policy_details

        
        ns = {'ns': 'http://guidewire.com/pc/gx/gw.webservice.pc.pc1000.gxmodel.policyperiodmodel'}

        
        root = ET.fromstring(xml_string)
        period_end = root.find('.//ns:PeriodEnd', ns)
        if period_end is None:
            return None, None, None, None

        exp_date = datetime.fromisoformat(period_end.text.replace("Z", "+00:00"))
        effective_date = root.find('.//ns:OriginalEffectiveDate', ns)
        if effective_date is not None:
            eff_date = datetime.fromisoformat(
                effective_date.text.replace("Z", "+00:00")
            )
        else:
            eff_date = None

        print("Effective Date from Policy Details:", 
              effective_date.text if effective_date is not None else None)
        print("Expiration Date from Policy Details:", exp_date)


        sub_date = datetime.now(timezone.utc)

        if loss_date_str.endswith("Z"):
            loss_date_str = loss_date_str.replace("Z", "+00:00")

        loss_date = datetime.fromisoformat(loss_date_str)

        print("Submission Date (Current UTC):", sub_date)
        print("Loss Date from Input:", loss_date)
        print("Effective Date:", eff_date)
        print("Expiration Date:", exp_date)

        if loss_date > sub_date:
            return "PolicyInvalid"
        
        if eff_date <= sub_date <= exp_date:

            # Loss date inside coverage period
            if eff_date <= loss_date <= exp_date:
                return "Valid"
            else:
                return "PolicyInvalid"

        else:
            six_months_after_exp = exp_date + timedelta(days=180)

            if sub_date <= six_months_after_exp:
                if eff_date <= loss_date <= exp_date:
                    return "Eligible"
                else:
                    return "PolicyInvalid"
            else:
                if eff_date <= loss_date <= exp_date:
                    return "Not Eligible"
                else:
                    return "PolicyInvalid"

    except Exception as e:
        return f"Error: {str(e)}"


    except Exception as e:
        return f"Error: {str(e)}"