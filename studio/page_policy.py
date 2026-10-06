"""Automatic page layout on owned copies, preserving deliberate manual timing."""
import copy
from studio.smart_pages import intelligent_pages


def prepare_pages(project, automatic=True):
    candidate = copy.deepcopy(project)
    if automatic and candidate.page_layout_mode != 'manual' and candidate.notes:
        result = intelligent_pages(candidate)
        if result['oversized_words']:
            warning = 'Large word/melisma groups kept intact during page optimization.'
            if warning not in candidate.warnings:
                candidate.warnings.append(warning)
        candidate.page_layout_mode = 'automatic'
    return candidate
