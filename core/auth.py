from enum import Enum

class Authentications(Enum):
  API = 1
  UI = 2
  OTHER = 3

def type_of_auth(token):
  if len(token.split(".")) == 3:
    return Authentications.UI
  elif len(token) == 40:
    return Authentications.API
  else:
    return Authentications.OTHER
