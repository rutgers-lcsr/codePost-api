from rest_framework.renderers import DocumentationRenderer
from rest_framework.compat import (
  coreapi, pygments_css
)
from django.template import loader
import copy
import json
import collections

import settings

class CustomRenderer(DocumentationRenderer):
  media_type = 'text/html'
  format = 'html'
  charset = 'utf-8'
  template = 'rest_framework/docs/index.html'
  error_template = 'rest_framework/docs/error.html'
  code_style = 'emacs'
  languages = ['curl', 'python']
  # languages = ['shell', 'python-old', 'javascript']

  def get_context(self, data, request):

    # 'data' is a coreapi.Document object
    # **** actually, here it prints <class 'coreapi.document.Document'
    print (type(data))
    # If we want to manipulate which sections and endpoints get rendered
    # (e.g. remove token-refresh section; hide the delete endpoints)
    # Then we can modify this Object directly
    # However, I'm having trouble doing that
    # See the documentation here: https://core-api.github.io/python-client/api-guide/document/

    # There may be other ways to achieve similar ends (via permissioning or otherwise)
    # We could also update the Django Rest Framework /docs templates if we have trouble
    # with coreapi
    return {
      'document': data,
      'langs': self.languages,
      'lang_htmls': ["docs/langs/%s.html" % l for l in self.languages],
      'lang_intro_htmls': ["docs/langs/%s-intro.html" % l for l in self.languages],
      'code_style': pygments_css(self.code_style),
      'request': request
    }

  def render(self, data, accepted_media_type=None, renderer_context=None):
    if isinstance(data, coreapi.Document):
      template = loader.get_template(self.template)
      context = self.get_context(data, renderer_context['request'])
      return template.render(context, request=renderer_context['request'])
    else:
      template = loader.get_template(self.error_template)
      context = {
          "data": data,
          "request": renderer_context['request'],
          "response": renderer_context['response'],
          "debug": settings.DEBUG,
      }
      return template.render(context, request=renderer_context['request'])