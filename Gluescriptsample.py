import boto3
import json
import gnupg
import time
from datetime import datetime, timezone
import zipfile
import contextlib
import sys
from io import BytesIO
import os
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql import SQLContext
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
#@params: [JOB_NAME]
sc = SparkContext()
args = getResolvedOptions(sys.argv, ['JOB_NAME'])
glueContext = GlueContext(sc)
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

print('Imported Package Successfully')

s3_resource = boto3.resource('s3')
s3 = boto3.client('s3')
switcher =  { "744849271214" : "dev" }
sts_client =  boto3.client('sts')
etl_account = sts_client.get_caller_identity()
etl_account_id = etl_account['Account']
etl_env = switcher[etl_account_id]
landing_bucket = "datasvc-"+etl_env+"-landing-zone"
curated_bucket = "datasvc-"+etl_env+"-curated-zone"
config_bucket = "datasvc-"+etl_env+"-config-zone"
landing_folder='telematics_gtc_raw.db/'
mft_folder='inbound_mft/telematics_gtc/'
proc_folder = landing_folder + 'processed_files/'
error_folder = landing_folder + 'error_files/'
working_Dir='working_dir/' + landing_folder
PGP_PrivateKey= working_Dir + 'pgp_keys/GTC_QA_PGP_PrivateKey.asc'
decrypted_Files = working_Dir + 'decrypted_files/'
unzipped_Files = working_Dir + 'unzipped_files/'
#bad_files = working_Dir + 'Bad-Files/'

try :
    zipped_keys =  s3.list_objects_v2(Bucket=landing_bucket,Prefix =mft_folder, Delimiter = "/")
    print(zipped_keys)
    while zipped_keys['IsTruncated'] :
        print("While loop started")
        for file in zipped_keys['Contents']:
            LastModified_date = file['LastModified']
            currdatetime = datetime.now(timezone.utc)
            diff = currdatetime-LastModified_date
            diff_minutes = (diff.days * 24 * 60) + (diff.seconds/60)
            files=file['Key']
            
            print(files)
            file_name = files.split("/")[-1]
            file_names =file_name.split(".")[0]
            zip_file_name = file_names + ".zip"
            print("Inbound File name is "+zip_file_name)
            proc_files = proc_folder + file_name
            
            if not files.endswith('/') and round(diff_minutes) >= 30  :

                s3_resource.meta.client.download_file(landing_bucket,files,'/tmp/encrypted.pgp')
                s3_resource.meta.client.download_file(config_bucket,PGP_PrivateKey,'/tmp/private.key')
                
                gpg = gnupg.GPG(gnupghome='/tmp')
                key_data = open('private.key').read()
                priv_key = gpg.import_keys(key_data)
                
                with open('/tmp/'+ 'encrypted.pgp','rb') as encrp_file :
                    status = gpg.decrypt_file(encrp_file,passphrase='SpHonda246',output=zip_file_name)
                
                if status.ok:
                    print('ElGamal Decryption Successful')
                    print("file_name",zip_file_name)
                    dec_files = decrypted_Files + zip_file_name 
                    print("files",dec_files)
                    s3_resource.meta.client.upload_file('/tmp/' + zip_file_name,config_bucket,dec_files )
                    
                    zip_obj = s3_resource.Object(bucket_name=config_bucket, key=dec_files)
                    print("zip_obj",zip_obj)
                
                    buffer = BytesIO(zip_obj.get()["Body"].read())
                    print("buffer",buffer)
                    
                    if zipfile.is_zipfile(buffer):
                        z = zipfile.ZipFile(buffer,mode='r')
                        #print("The zip file value z is",z)
                        for filename in z.namelist():
                            file_info = z.getinfo(filename)
                    
                            s3_resource.meta.client.upload_fileobj(
                                z.open(filename),
                                Bucket=config_bucket,
                                Key=unzipped_Files + f'{filename}')
                        z.close()  # important!
                        buffer.seek(0)
                
                    else:
                        print('file {file} is not a zip file'.format(file = files))
                        error_files = error_folder + file_name 
                        s3_resource.meta.client.upload_file('/tmp/' + file_name,landing_bucket,error_files )
                
        ContToken = zipped_keys['NextContinuationToken']        
        print(ContToken)        
        zipped_keys =  s3.list_objects_v2(Bucket=landing_bucket,Prefix = mft_folder, Delimiter = "/",ContinuationToken=ContToken)      
        print(zipped_keys)
        
    #Process for less rhan 1000 files 
    for file in zipped_keys['Contents']:
        LastModified_date = file['LastModified']
        print("LastModified_date",LastModified_date)
        currdatetime = datetime.now(timezone.utc)
        print("currdatetime",currdatetime)
        diff = currdatetime-LastModified_date
        diff_minutes = (diff.days * 24 * 60) + (diff.seconds/60)
        files=file['Key']
        
        file_name = files.split("/")[-1]
        print("file_name",file_name)
        file_names =file_name.split(".")[0]
        print("file_names",file_names)
        zip_file_name = file_names + ".zip"
        print("Inbound File name is "+zip_file_name)
        proc_files = proc_folder + file_name
        print("proc_files",proc_files)
        
        
        if not files.endswith('/') and round(diff_minutes) >= 30  :

            s3_resource.meta.client.download_file(landing_bucket,files,'/tmp/encrypted.pgp')
            s3_resource.meta.client.download_file(config_bucket,PGP_PrivateKey,'/tmp/private.key')
            
            gpg = gnupg.GPG(gnupghome='/tmp')
            key_data = open('private.key').read()
            priv_key = gpg.import_keys(key_data)
            
            with open('/tmp/'+ 'encrypted.pgp','rb') as encrp_file :
                status = gpg.decrypt_file(encrp_file,passphrase='SpHonda246',output=zip_file_name)
            
            if status.ok:
                print('ElGamal Decryption Successful')
                print("file_name",zip_file_name)
                dec_files = decrypted_Files + zip_file_name 
                print("files",dec_files)
                s3_resource.meta.client.upload_file('/tmp/' + zip_file_name,config_bucket,dec_files )
                
                zip_obj = s3_resource.Object(bucket_name=config_bucket, key=dec_files)
                print("zip_obj",zip_obj)
            
                buffer = BytesIO(zip_obj.get()["Body"].read())
                print("buffer",buffer)
                #if fnmatch.fnmatch(zfn,"*.zip")
                
                if zipfile.is_zipfile(buffer):
                    #print(buffer)
                    z = zipfile.ZipFile(buffer,mode='r')
                    #print("The zip file value z is",z)
                    for filename in z.namelist():
                        file_info = z.getinfo(filename)
                
                        s3_resource.meta.client.upload_fileobj(
                            z.open(filename),
                            Bucket=config_bucket,
                            Key=unzipped_Files + f'{filename}')
                    z.close()  # important!
                    buffer.seek(0)
                    copy_source = {'Bucket': landing_bucket,'Key': files }
                    s3_resource.meta.client.copy(copy_source,Bucket=landing_bucket,Key=proc_files)
                    s3.delete_object(Bucket=landing_bucket, Key=files)
                    print("Message and temp file deleted sucessfully")

                    
                else:
                    print('file {file} is not a zip file'.format(file = files))
                    error_files = error_folder + file_name 
                    print("error_files",error_files)
                    s3_resource.meta.client.upload_file('/tmp/'+ 'encrypted.pgp',landing_bucket,error_files )
                    s3.delete_object(Bucket=landing_bucket, Key=files)
                #delete_message = sqs_client.delete_message(QueueUrl=sqs_gtc_url['QueueUrl'], ReceiptHandle= msg_handle)
            print("Try block completed")
        #time.sleep(20)
        
    def extract_json(keyword,file_list_new):
        if keyword in file_list_new:
            print("DTCA Value is :",file_list_new)
            copy_source = {
                'Bucket': config_bucket,
                'Key': file_list_new
                }
            jsonfilename =  file_list_new.split("/")[-1]
            print("filename as :",jsonfilename)
            Key_new = landing_folder + keyword.lower() +'/' + jsonfilename 
            error_Key_new = error_folder + keyword.lower() +'/' + jsonfilename
            print("Key_new value is :",Key_new)
            s3_resource.meta.client.download_file(config_bucket,file_list_new,'/tmp/filename')
            with open('/tmp/'+ 'filename','rb') as file:
                try:
                    json.load(file) 
                except json.decoder.JSONDecodeError:  
                    print("Invlaid JSON file moving to error folder")                
                    s3_resource.meta.client.copy(copy_source,Bucket=landing_bucket,Key=error_Key_new)
                else:
                    print("VALID JSON file moving to landing folder") 
                    s3_resource.meta.client.copy(copy_source,Bucket=landing_bucket,Key=Key_new)
            s3.delete_object(Bucket=config_bucket,Key=dec_files)
            s3.delete_object(Bucket=config_bucket,Key=file_list_new)
    
    

    json_files = s3.list_objects_v2(Bucket=config_bucket,
                                                      Prefix=unzipped_Files)
    for key in json_files['Contents']:
        file_list_new = key['Key']
        print("file_list1 Value is: ",file_list_new)
        keyword_list = ['DTCA','DTCB','VI','TL','WL']
        for key_word in keyword_list:
            extract_json(key_word,file_list_new)
                        

    
except Exception as e:
    print("Failed" + e )
