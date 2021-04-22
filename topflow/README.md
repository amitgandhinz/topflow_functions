# GetThatCashMoney

## Setup Environment Variables
1. create an `.env.yaml` file from the `sample.env.yaml` and populate with your Twitter and Robinhood Credentials
2. Create a `serviceAccountKey.json` file from your Firebase configuration
3. When running locally, run `python yaml_to_env.py` and load your environment variables to your local shell.

## Add a new symbol to the watchlist
python3 main.py 'add' 'SYMBOL' 'PRICE' 'TWEETID' 'QUALITY'

## Update symbols in the watchlist
python3 main.py 'update'

## Deploy to Google Cloud Functions
- gcloud functions deploy update_flow --env-vars-file .env.yaml --runtime python38 --trigger-http
- gcloud functions deploy twitter --env-vars-file .env.yaml --runtime python38 --trigger-http --allow-unauthenticated

## Backup or Restore a Firestore Database
- https://stackoverflow.com/questions/46746604/firestore-new-database-how-do-i-backup
-   EXPORT ALL: gcloud firestore export gs://optionsflow_backup
-   IMPORT ALL: gcloud firestore import gs://optionsflow_backup/2021-03-23T18:28:18_84965/ 

