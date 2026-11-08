import struct
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models

MAX_BOOK_COVER_IMAGE_SIZE_BYTES = 2 * 1024 * 1024
MAX_BOOK_COVER_IMAGE_WIDTH = 1200
MAX_BOOK_COVER_IMAGE_HEIGHT = 1600
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_START_OF_IMAGE = b"\xff\xd8"
JPEG_FRAME_MARKERS = {
    b"\xc0",
    b"\xc1",
    b"\xc2",
    b"\xc3",
    b"\xc5",
    b"\xc6",
    b"\xc7",
    b"\xc9",
    b"\xca",
    b"\xcb",
    b"\xcd",
    b"\xce",
    b"\xcf",
}


class BookStatus(models.TextChoices):
    WILL_READ = "will_read", "Will read"
    READING = "reading", "Reading"
    READ = "read", "Read"
    DELETED = "deleted", "Deleted"


ACTIVE_BOOK_STATUSES = (BookStatus.WILL_READ, BookStatus.READING, BookStatus.READ)


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Author(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(
        Author,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="books",
    )
    language = models.ForeignKey(
        Language,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="books",
    )
    cover_image = models.FileField(
        blank=True,
        null=True,
        upload_to="book-covers/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png"])],
        help_text="Upload a JPG or PNG cover up to 2 MB and 1200×1600 pixels.",
    )
    status = models.CharField(
        max_length=20,
        choices=BookStatus.choices,
        default=BookStatus.WILL_READ,
        db_index=True,
    )
    tags = models.ManyToManyField(Tag, related_name="books", blank=True)
    started_at = models.DateField(blank=True, null=True)
    finished_at = models.DateField(blank=True, null=True)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Use a 1-10 scale, in steps of 0.5",
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("10"))],
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "title"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=10) | models.Q(rating__isnull=True),
                name="book_rating_between_1_and_10",
            )
        ]

    def __str__(self) -> str:
        if self.author:
            return f"{self.title} by {self.author}"
        return self.title

    def clean(self):
        super().clean()
        _validate_uploaded_image(self.cover_image, "cover_image", "Cover")


class Movie(models.Model):
    title = models.CharField(max_length=255)
    poster = models.FileField(
        blank=True,
        null=True,
        upload_to="movie-posters/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png"])],
        help_text="Upload a JPG or PNG poster up to 2 MB and 1200×1600 pixels.",
    )
    language = models.ForeignKey(
        Language,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="movies",
    )
    watched_at = models.DateField(blank=True, null=True, db_index=True)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        blank=True,
        null=True,
        help_text="Use a 1-10 scale, in steps of 0.5",
        validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("10"))],
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-watched_at", "title"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=10) | models.Q(rating__isnull=True),
                name="movie_rating_between_1_and_10",
            )
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self):
        super().clean()
        _validate_uploaded_image(self.poster, "poster", "Poster")


def _validate_uploaded_image(image, field_name, noun):
    if not image:
        return

    if image.size > MAX_BOOK_COVER_IMAGE_SIZE_BYTES:
        raise ValidationError({field_name: f"{noun} images must be 2 MB or smaller."})

    try:
        width, height = _read_book_cover_dimensions(image)
    except ValueError as exc:
        raise ValidationError({field_name: "Upload a valid JPG or PNG image."}) from exc

    if width > MAX_BOOK_COVER_IMAGE_WIDTH or height > MAX_BOOK_COVER_IMAGE_HEIGHT:
        raise ValidationError(
            {field_name: f"{noun} images must be no larger than 1200×1600 pixels."}
        )


def _read_book_cover_dimensions(uploaded_file):
    uploaded_file.seek(0)
    signature = uploaded_file.read(8)
    uploaded_file.seek(0)

    if signature.startswith(PNG_SIGNATURE):
        return _read_png_dimensions(uploaded_file)
    if signature.startswith(JPEG_START_OF_IMAGE):
        return _read_jpeg_dimensions(uploaded_file)
    raise ValueError("Unsupported image format")


def _read_png_dimensions(uploaded_file):
    uploaded_file.seek(16)
    data = uploaded_file.read(8)
    uploaded_file.seek(0)
    if len(data) != 8:
        raise ValueError("PNG header too short")
    width, height = struct.unpack(">II", data)
    if width <= 0 or height <= 0:
        raise ValueError("Invalid PNG dimensions")
    return width, height


def _read_jpeg_dimensions(uploaded_file):
    uploaded_file.seek(2)
    while True:
        marker_prefix = uploaded_file.read(1)
        if not marker_prefix:
            raise ValueError("JPEG size not found")
        if marker_prefix != b"\xff":
            continue

        marker = uploaded_file.read(1)
        while marker == b"\xff":
            marker = uploaded_file.read(1)
        if not marker:
            raise ValueError("JPEG size not found")
        if marker in {b"\xd8", b"\xd9"}:
            continue

        length_data = uploaded_file.read(2)
        if len(length_data) != 2:
            raise ValueError("JPEG segment too short")
        segment_length = struct.unpack(">H", length_data)[0]
        if segment_length < 2:
            raise ValueError("Invalid JPEG segment length")

        if marker in JPEG_FRAME_MARKERS:
            precision_data = uploaded_file.read(1)
            size_data = uploaded_file.read(4)
            if len(precision_data) != 1 or len(size_data) != 4:
                raise ValueError("JPEG size not found")
            height, width = struct.unpack(">HH", size_data)
            uploaded_file.seek(0)
            if width <= 0 or height <= 0:
                raise ValueError("Invalid JPEG dimensions")
            return width, height

        uploaded_file.seek(segment_length - 2, 1)
