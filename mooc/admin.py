from django.contrib import admin
from mooc.models import *
# Custom admin models


class ProductAdmin(admin.ModelAdmin):
  search_fields = ('name', 'offeredBy')

admin.site.register(Product, ProductAdmin)

class TierAdmin(admin.ModelAdmin):
  search_fields = ('name', 'product__name')

admin.site.register(Tier, TierAdmin)


class OrderAdmin(admin.ModelAdmin):
  search_fields = ('user__email', 'product__name')

  def get_readonly_fields(self, request, obj=None):
    if obj:  # editing an existing object
      return self.readonly_fields + ('user',)
    return self.readonly_fields

admin.site.register(Order, OrderAdmin)


class PayoutAdmin(admin.ModelAdmin):
  search_fields = ('reviewer__email', 'status')

  def get_readonly_fields(self, request, obj=None):
    if obj:  # editing an existing object
      return self.readonly_fields + ('reviewer',)
    return self.readonly_fields


admin.site.register(Payout, PayoutAdmin)


class CreditAdmin(admin.ModelAdmin):
  search_fields = ('user__email', 'assignment__name')

  def get_readonly_fields(self, request, obj=None):
    if obj:  # editing an existing object
      return self.readonly_fields + ('user', 'submission')
    return self.readonly_fields

admin.site.register(Credit, CreditAdmin)


class ReviewAdmin(admin.ModelAdmin):

  def get_readonly_fields(self, request, obj=None):
    if obj:  # editing an existing object
      return self.readonly_fields + ('reviewer',)
    return self.readonly_fields

admin.site.register(Review, ReviewAdmin)
