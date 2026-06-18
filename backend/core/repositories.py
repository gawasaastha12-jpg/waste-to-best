# backend/core/repositories.py
from typing import TypeVar, Generic, Type, Optional, List, Any
from django.db import models

T = TypeVar('T', bound=models.Model)

class BaseRepository(Generic[T]):
    model: Type[T] = None

    def __init__(self) -> None:
        if self.model is None:
            raise NotImplementedError("Subclasses of BaseRepository must define the 'model' class attribute.")

    def get_by_id(self, pk: Any) -> Optional[T]:
        """
        Retrieves a single model instance by its primary key.
        """
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            return None

    def list_all(self) -> List[T]:
        """
        Returns all instances of the model.
        """
        return list(self.model.objects.all())

    def filter_by(self, **kwargs: Any) -> models.QuerySet:
        """
        Filters instances matching parameters.
        Returns a QuerySet to allow further chaining and DRF pagination support.
        """
        return self.model.objects.filter(**kwargs)

    def create(self, **fields: Any) -> T:
        """
        Creates and saves a new model instance.
        """
        instance = self.model(**fields)
        instance.save()
        return instance

    def update(self, instance: T, **fields: Any) -> T:
        """
        Updates fields on an existing model instance.
        """
        for attr, value in fields.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def delete(self, instance: T) -> None:
        """
        Removes a model instance from the database.
        """
        instance.delete()

