# GetThatCashMoney


## LOCAL DEV ENV

```sh
brew install python3
pip3 install virtualenv
virtualenv -p python3 .
source ./bin/activate

cd topflow
pip install -r requirements.txt
```


## Setup Environment Variables
1. create an `.env.yaml` file from the `sample.env.yaml` and populate with your Twitter and Robinhood Credentials
2. Create a `.GOOGLE.json` file using your Firebase configuration
3. Load your credentials file for Google so your local env can have access to firebase.  In production, give your google function a service account to firebase.
```sh
export GOOGLE_APPLICATION_CREDENTIALS=.GOOGLE.json
```

4. When running locally, run 

```sh
python yaml_to_env.py
``` 

then, copy paste the output to load your environment variables to your local shell.

## Add a new symbol to the watchlist

### via Command Line:
```sh
python3 main.py 'add' 'SYMBOL' 'PRICE' 'TWEETID' 'QUALITY' 
```

For Example: 
```sh
python3 main.py 'add' 'ADSK 210716C290' '15.60' '1385299336263831555' '3'
```

### via Twitter:
```sh
$HOME 210416C31 at $199.99 [$$$]
```

## Update symbols in the watchlist
```sh
python3 main.py 'update'
```

## Install Google Cloud SDK
- ```sh curl https://sdk.cloud.google.com | bash```
- ```sh gcloud init```
- then log in to your google cloud account in the browser
- then select the project to link to where your firestore and cloud functions are connected to

## Deploy to Google Cloud Functions

Update Flow Data
```sh
gcloud functions deploy update_flow \
--env-vars-file .env.yaml \
--runtime python38 \
--trigger-http 
```

Trigger from Twitter Tweets
```sh
gcloud functions deploy twitter \
--env-vars-file .env.yaml \
--runtime python38 \
--trigger-http \
--allow-unauthenticated 
```

Trigger from Firestore Create Records
```sh
gcloud functions deploy newFlowTrigger \
--env-vars-file .env.yaml \
--runtime python39 \
--trigger-event "providers/cloud.firestore/eventTypes/document.create" \
--trigger-resource "projects/optionstracker-aa7f7/databases/(default)/documents/users/{userid}/journal/{symbol}"
```

## Backup or Restore a Firestore Database
https://stackoverflow.com/questions/46746604/firestore-new-database-how-do-i-backup

EXPORT ALL: 
```sh 
gcloud firestore export gs://optionsflow_backup 
```

IMPORT ALL: 
```sh 
gcloud firestore import gs://optionsflow_backup/2021-03-23T18:28:18_84965/ 
```



