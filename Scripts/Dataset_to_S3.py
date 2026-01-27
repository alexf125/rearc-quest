import os
import requests
import boto3
from bs4 import BeautifulSoup
from datetime import datetime, UTC

# Could parameterize this script to allow for additional flexability, but it's unecessary for this exercise
# Variable for the web directory url
dataset_url = "https://download.bls.gov/pub/time.series/pr/"

# Variable for the User-Agent header to comply with BLS bot usage statement
headers = {'User-Agent': "Please contact alexferguson125@yahoo.com for any inquiries."}

# AWS Credentials from Environment Variable
aws_access_key_id = str(os.getenv('AWS_ACCESS_KEY_ID'))
aws_secret_access_key = str(os.getenv('AWS_SECRET_ACCESS_KEY'))
bucket_name = "af-rearc-quest"
s3_path = "BLS/"

# This function takes html for the web directory, parses it for file names, and returns an array with the file names in the directory
def parse_directory(html):
    # List for File Names from web directory
    file_names = []
    file_paths = []

    # Sets up object for html parsing
    soup = BeautifulSoup(html, "html.parser")

    # Loops through all <a></a> html tags
    for link in soup.find_all('a'):
        # Checks if the link isn't for the Parent Directory and add it to the list
        if(link.text != '[To Parent Directory]'):
            file_names.append(link.text)
            file_paths.append(s3_path+link.text)

    # Prints file name list for debugging and return list
    print(file_names)
    return file_names, file_paths

# This function takes file information from the web directory, compares it to the files in the S3 bucket,
# determines if the file should be uploaded (doesn't already exist or has been updated recently),
# then either uploads the file or states that there's no new or updated file to upload.
# Archival process of old files can be added if necessary, but is unnecessary for this exercise
def s3_transfer(source_file, file_content_type, file_name, file_last_modified):
    # Dictionary for S3 File Name + Last Modified Date
    s3_files = {}

    # Create an S3 resource for metadata retrieval
    s3 = boto3.resource("s3",aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)

    # Create and S3 Client for file upload
    s3_client = boto3.client("s3",aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)

    # Accesses S3 bucket, retrieves File Name and Last Modified Date, and adds them to the dictionary
    bucket = s3.Bucket(bucket_name)
    for file in bucket.objects.all():
        s3_files[file.key] = file.last_modified

    # Print S3 File Dictionary for debugging (Disabled unless needed)
    # print(s3_files)

    # Check if the file name isn't in the S3 File Dictionary,
    # then it's new and should be uploaded
    if (file_name not in s3_files):
        print("Uploading new file...")
        s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=source_file, ContentType=file_content_type)
        print(f"New file {file_name} uploaded\r\n")
    # Else If the file name is in the S3 File Dictionary and the Source Last Modified Sate is more recent then S3 Last Modified Date,
    # then it's been updated and should be uploaded
    elif (file_name in s3_files and file_last_modified > s3_files[file_name]):
        print("Uploading updated file...")
        s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=source_file, ContentType=file_content_type)
        print(f"Updated file {file_name} uploaded\r\n")
    # Else no new or updated files to be uploaded
    else:
        print("No new or updated files.\r\n")

# This function removes any file from the S3 bucket that has been deleted from the web directory
def s3_deletes(source_file_list):
    # Dictionary for S3 File Name + Last Modified Date
    s3_files = []

    # Create an S3 resource for metadata retrieval
    s3 = boto3.resource("s3",aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)

    # Create and S3 Client for file upload
    s3_client = boto3.client("s3",aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)

    # Accesses S3 bucket, retrieves File Nams and adds them to the List
    bucket = s3.Bucket(bucket_name)
    for file in bucket.objects.filter(Prefix=s3_path):
        s3_files.append(file.key)

    # Print S3 File List for debugging (Disabled unless needed)
    # print(s3_files)

    # Check if the S3 file name isn't in the Web Directory,
    # then it's been deleted and should be removed from S3
    delete_from_s3 = [file for file in s3_files if file not in source_file_list]

    # Print Delete from S3 File List for debugging (Disabled unless needed)
    # print(delete_from_s3)

    # Loop through Delete from S3 list and delete the file
    for file in delete_from_s3:
        try:
            print(f"Deleting file {file} from S3 (no longer in source)...")
            response = s3_client.delete_object(Bucket=bucket_name, Key=file)
            print(f"{file} has been deleted\r\n")
            # Print response for debugging (Disabled unless needed)
            # print(response)
        except Exception as e:
            print(f"Error deleting object: {e}")
    # If no files to be deleted
    if len(delete_from_s3) == 0:
        print("No files to be deleted.\r\n")

# Main function that runs everything:
# 1. Runs a request to grab the html of the directory
# 2. Calls Parsing function (parse_directory) and passes the returned html to the parsing function
# 3. Grabs the file name list from the parsing function and loop through it
# 4. Creates the URL for the current file in the loop
# 5. Requests the file
# 6. Grab the Last Modified Date and Content Type of the file from the repsonse header
# 7. Convert Last Modified Date string to UTC Date for comparison to S3 Last Modified Date
# 8. Calls the S3 Transfer function (s3_transfer) and passes the file's content, type, name, and last modified date
# 9. Deletes any S3 file that no longer exists in the web directory
def main():
    try:
        response = requests.get(dataset_url, headers=headers)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    if response.ok:
        file_names, file_paths = parse_directory(response.text)
        for file in file_names:
            file_url = dataset_url + file
            print(file_url)
            try:
                response = requests.get(file_url, headers=headers)
                if response.ok:
                    file_last_modified = response.headers.get('Last-Modified')
                    file_content_type = response.headers.get('Content-Type')
                    file_last_modified = datetime.strptime(file_last_modified, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=UTC)
                    s3_transfer(response.content, file_content_type, s3_path+file, file_last_modified)
                else:
                    print(f"Error accessing file ({file}): {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
        s3_deletes(file_paths)
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    main()