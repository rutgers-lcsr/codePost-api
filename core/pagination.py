from rest_framework.pagination import PageNumberPagination

class DefaultPagination(PageNumberPagination):
    page_size = 150
    page_size_query_param = 'page_size'
    max_page_size = 1000

# For large objects, e.g., test results 
class LargeObjectsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100