"""
Generic pagination helper.

Kept separate from any one endpoint so the same logic covers /neighborhoods
today and any other list endpoint later (e.g. a future /zones or /projects)
without copy-pasting the slicing math.
"""
import math
from typing import List, Sequence, TypeVar

T = TypeVar("T")


def paginate(items: Sequence[T], page: int, page_size: int) -> dict:
    """
    Slice `items` into one page. `page` is 1-indexed. A page number past the
    end returns an empty `items` list rather than raising — callers scrolling
    past the last page get a clean "nothing more here", not an error.
    """
    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "items": list(items[start:end]),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }
