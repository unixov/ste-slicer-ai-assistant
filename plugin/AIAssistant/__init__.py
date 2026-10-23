from . import AIAssistant


def getMetaData():
    return {
        "stage": {
            "name": "AI Assistant",
            "weight": 1000,
        }
    }


def register(app):
    return {"stage": AIAssistant.AssistantStage()}
