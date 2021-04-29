import os
from twitivity import Activity



if __name__ == "__main__":
    activity = Activity()

    activity.refresh(
        webhook_id='1373111214344179713'
        )
    print(
        activity.register_webhook("https://us-central1-optionstracker-aa7f7.cloudfunctions.net/twitter")
    )
    print(activity.subscribe())


