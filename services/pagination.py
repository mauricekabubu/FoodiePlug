from django.core.paginator import Paginator


def paginate_queryset(request, queryset, per_page, page_param="page"):
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get(page_param))
    page_query = request.GET.copy()
    page_query.pop(page_param, None)
    page_links = [
        {
            "number": number,
            "current": number == page_obj.number,
            "gap": not isinstance(number, int),
        }
        for number in paginator.get_elided_page_range(
            page_obj.number,
            on_each_side=1,
            on_ends=1,
        )
    ]
    return {
        "page_obj": page_obj,
        "page_links": page_links,
        "page_query": page_query.urlencode(),
    }
