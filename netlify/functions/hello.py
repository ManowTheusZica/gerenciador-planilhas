"""
Função de teste mínima para verificar se Python Functions funcionam no Netlify.
"""
import json


def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "message": "Hello from Python Function!",
            "path": event.get("path", "/"),
            "method": event.get("httpMethod", "GET"),
        }),
        "isBase64Encoded": False,
    }
