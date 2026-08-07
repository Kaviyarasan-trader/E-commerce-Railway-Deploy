from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import UserProfile, Product, ProductImage, Catagory, ProductRating, ProductRatingMedia
from .utils import delete_image_file


@receiver(pre_save, sender=UserProfile)
def delete_old_profile_picture(sender, instance, **kwargs):
    """Remove the previous picture file from disk when the photo is changed or cleared."""
    if not instance.pk:
        return
    try:
        old = UserProfile.objects.get(pk=instance.pk)
    except UserProfile.DoesNotExist:
        return
    old_name = old.profile_picture.name if old.profile_picture else None
    new_name = instance.profile_picture.name if instance.profile_picture else None
    if old_name and old_name != new_name:
        delete_image_file(old_name, exclude=instance)


@receiver(post_delete, sender=UserProfile)
def delete_profile_picture_on_delete(sender, instance, **kwargs):
    """Remove the picture file from disk when the profile (and its user) is deleted."""
    if instance.profile_picture:
        delete_image_file(instance.profile_picture)


@receiver(pre_save, sender=Product)
def delete_old_product_cover(sender, instance, **kwargs):
    """Remove the old cover file from disk when a product's cover is replaced or cleared."""
    if not instance.pk:
        return
    try:
        old = Product.objects.get(pk=instance.pk)
    except Product.DoesNotExist:
        return
    old_name = old.product_image.name if old.product_image else None
    new_name = instance.product_image.name if instance.product_image else None
    if old_name and old_name != new_name:
        delete_image_file(old_name, exclude=instance)


@receiver(post_delete, sender=Product)
def delete_product_cover_on_delete(sender, instance, **kwargs):
    """Remove the cover file from disk when a product is deleted."""
    if instance.product_image:
        delete_image_file(instance.product_image)


@receiver(post_delete, sender=ProductImage)
def delete_product_gallery_image_on_delete(sender, instance, **kwargs):
    """Remove the gallery image file from disk when a ProductImage row is removed."""
    if instance.image:
        delete_image_file(instance.image)


@receiver(pre_save, sender=Catagory)
def delete_old_category_image(sender, instance, **kwargs):
    """Remove the old image file from disk when a category image is replaced or cleared."""
    if not instance.pk:
        return
    try:
        old = Catagory.objects.get(pk=instance.pk)
    except Catagory.DoesNotExist:
        return
    old_name = old.image.name if old.image else None
    new_name = instance.image.name if instance.image else None
    if old_name and old_name != new_name:
        delete_image_file(old_name, exclude=instance)


@receiver(post_delete, sender=Catagory)
def delete_category_image_on_delete(sender, instance, **kwargs):
    """Remove the image file from disk when a category is deleted."""
    if instance.image:
        delete_image_file(instance.image)


@receiver(pre_save, sender=ProductRating)
def delete_old_rating_image(sender, instance, **kwargs):
    """Remove the previous image file from disk when a rating's photo is replaced or cleared."""
    if not instance.pk:
        return
    try:
        old = ProductRating.objects.get(pk=instance.pk)
    except ProductRating.DoesNotExist:
        return
    old_name = old.image.name if old.image else None
    new_name = instance.image.name if instance.image else None
    if old_name and old_name != new_name:
        delete_image_file(old_name, exclude=instance)


@receiver(post_delete, sender=ProductRating)
def delete_rating_image_on_delete(sender, instance, **kwargs):
    """Remove the photo file (and any media files) from disk when a rating is deleted."""
    if instance.image:
        delete_image_file(instance.image)


@receiver(pre_save, sender=ProductRatingMedia)
def delete_old_rating_media_file(sender, instance, **kwargs):
    """Remove the previous media file from disk when a rating media file is replaced or cleared."""
    if not instance.pk:
        return
    try:
        old = ProductRatingMedia.objects.get(pk=instance.pk)
    except ProductRatingMedia.DoesNotExist:
        return
    old_name = old.file.name if old.file else None
    new_name = instance.file.name if instance.file else None
    if old_name and old_name != new_name:
        delete_image_file(old_name, exclude=instance)


@receiver(post_delete, sender=ProductRatingMedia)
def delete_rating_media_file_on_delete(sender, instance, **kwargs):
    """Remove the media file from disk when a ProductRatingMedia row is deleted."""
    if instance.file:
        delete_image_file(instance.file)
