# backend/classification/constants.py
from django.db import models

class CategoryChoices(models.TextChoices):
    PLASTIC = 'Plastic', 'Plastic'
    PAPER = 'Paper', 'Paper'
    GLASS = 'Glass', 'Glass'
    METAL = 'Metal', 'Metal'
    ORGANIC = 'Organic', 'Organic'
    TEXTILE = 'Textile', 'Textile'
    E_WASTE = 'E-Waste', 'E-Waste'
    HAZARDOUS = 'Hazardous', 'Hazardous'
    MIXED_WASTE = 'Mixed Waste', 'Mixed Waste'

class ClassificationStatus(models.TextChoices):
    ANALYZING = 'ANALYZING', 'Analyzing'
    PENDING_CONFIRMATION = 'PENDING_CONFIRMATION', 'Pending Confirmation'
    PENDING_CLARIFICATION = 'PENDING_CLARIFICATION', 'Pending Clarification'
    CLASSIFIED = 'CLASSIFIED', 'Classified'
    FAILED = 'FAILED', 'Failed'
