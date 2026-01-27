import os
import requests
import boto3

# Could parameterize this script to allow for additional flexability, but it's unecessary for this exercise
# Variable for the api call url
api_url = "https://honolulu-api.datausa.io/tesseract/data.jsonrecords?cube=acs_yg_total_population_1&drilldowns=Year%2CNation&locale=en&measures=Population"
api_file_path = "honolulu-api/yearly_population.json"

# AWS Credentials from Environment Variable
aws_access_key_id = str(os.getenv('AWS_ACCESS_KEY_ID'))
aws_secret_access_key = str(os.getenv('AWS_SECRET_ACCESS_KEY'))
bucket_name = "af-rearc-quest"

# This function takes the json response and uploads it to the S3 bucket
def s3_transfer(data):
    # Create and S3 Client for file upload
    s3_client = boto3.client("s3",aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)

    # Uploads JSON file to S3
    print("Uploading file...")
    s3_client.put_object(Bucket=bucket_name, Key=api_file_path, Body=data, ContentType="application/json")
    print(f"File {api_file_path} uploaded\r\n")

# Main function that runs everything:
# 1. Runs an api request to grab the json file
# 2. Uploads file to S3
def main():
    try:
        response = requests.get(api_url)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    if response.ok:
        print(response.content)
        s3_transfer(response.content)
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    main()