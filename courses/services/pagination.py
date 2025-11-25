from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.conf import settings

class CustomPagination(PageNumberPagination):
    page_size = getattr(settings, 'DEFAULT_PAGE_SIZE', 9)
    page_size_query_param = 'page_size'
    max_page_size = getattr(settings, 'MAX_PAGE_SIZE', 100)


def paginate_queryset_or_list(request, queryset_or_list, serializer_class=None, serializer_kwargs=None):
    """
    Utility function to paginate a queryset or list for custom API endpoints.
    
    Args:
        request: Django request object
        queryset_or_list: Django queryset or list of items to paginate
        serializer_class: Optional serializer class to serialize items
        serializer_kwargs: Optional dict of kwargs to pass to serializer
    
    Returns:
        Response object with paginated data in the format:
        {
            "success": True,
            "data": [...],
            "message": "...",
            "count": total_count,
            "next": next_page_url or None,
            "previous": previous_page_url or None,
            "page_size": page_size,
            "current_page": current_page,
            "total_pages": total_pages
        }
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    # Get pagination settings
    default_page_size = getattr(settings, 'DEFAULT_PAGE_SIZE', 9)
    max_page_size = getattr(settings, 'MAX_PAGE_SIZE', 100)
    
    # Get page number and page size from query parameters
    try:
        page_number = int(request.query_params.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1
    
    try:
        page_size = int(request.query_params.get('page_size', default_page_size))
        # Enforce max page size
        page_size = min(page_size, max_page_size)
    except (ValueError, TypeError):
        page_size = default_page_size
    
    # Convert queryset to list if needed (for consistent pagination)
    if hasattr(queryset_or_list, '__iter__') and not isinstance(queryset_or_list, list):
        # It's a queryset, we can use it directly with Paginator
        paginator = Paginator(queryset_or_list, page_size)
    else:
        # It's already a list
        paginator = Paginator(queryset_or_list, page_size)
    
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    
    # Serialize data if serializer is provided
    if serializer_class:
        serializer_kwargs = serializer_kwargs or {}
        if hasattr(serializer_class, '__call__'):
            # It's a serializer class
            serializer = serializer_class(page.object_list, many=True, **serializer_kwargs)
            data = serializer.data
        else:
            # It's a function or callable
            data = [serializer_class(item, **serializer_kwargs) for item in page.object_list]
    else:
        # No serializer, return raw data (assumes items are already dicts)
        data = list(page.object_list)
    
    # Build pagination URLs
    base_url = request.build_absolute_uri().split('?')[0]
    query_params = request.query_params.copy()
    
    next_url = None
    if page.has_next():
        query_params['page'] = page.next_page_number()
        next_url = f"{base_url}?{query_params.urlencode()}"
    
    previous_url = None
    if page.has_previous():
        query_params['page'] = page.previous_page_number()
        previous_url = f"{base_url}?{query_params.urlencode()}"
    
    # Return paginated response
    return Response({
        "success": True,
        "data": data,
        "message": "Records retrieved successfully.",
        "count": paginator.count,
        "next": next_url,
        "previous": previous_url,
        "page_size": page_size,
        "current_page": page.number,
        "total_pages": paginator.num_pages
    })