from django.core.urlresolvers import reverse
from django.conf import settings
from django.contrib.gis.db import models

from leaderboard.locations.projected_geos import (
    ProjectedPoint,
    ProjectedPolygon,
    ProjectedMultiPolygon,
)


class CountryQuerySet(models.query.GeoQuerySet):
    """
    A queryset for Countries which will annotate
    the number of observations made in that country.
    """

    def annotate_observations(self):
        return self.annotate(
            observations=models.Sum('contributorrank__observations'),
        ).filter(observations__gt=0)


class CountryManager(models.GeoManager):
    """
    A model manager for Countries which allows you to
    query countries which are closest to a point.
    """

    def get_queryset(self):
        return CountryQuerySet(self.model, using=self._db)

    def nearest_to_point(self, point):
        country = self.get_queryset().distance(point).order_by('distance')[:1]

        if country.exists():
            return country.get()


class Country(models.Model):
    """
    A country as defined by:
    https://docs.djangoproject.com/en/1.8/ref/contrib/gis/
    tutorial/#defining-a-geographic-model
    """

    name = models.CharField(max_length=50)
    area = models.IntegerField()
    pop2005 = models.IntegerField('Population 2005')
    fips = models.CharField('FIPS Code', max_length=2)
    iso2 = models.CharField('2 Digit ISO', max_length=2, unique=True)
    iso3 = models.CharField('3 Digit ISO', max_length=3, unique=True)
    un = models.IntegerField('United Nations Code')
    region = models.IntegerField('Region Code')
    subregion = models.IntegerField('Sub-Region Code')
    lon = models.FloatField()
    lat = models.FloatField()
    geometry = models.MultiPolygonField(srid=settings.PROJECTION_SRID)

    objects = CountryManager()

    def __unicode__(self):
        return self.name

    @property
    def leaders_url(self):
        return reverse(
            'leaders-country-list',
            kwargs={'country_id': self.iso2},
        )


class TileManager(models.GeoManager):
    """
    A model manager for Tiles which allows you to
    query a Tile nearest to a point provided in easting/northing
    projected coordinates.
    """

    def get_or_create_nearest_tile(self, easting=None, northing=None,
                                   *args, **kwargs):
        # Round to the nearest tile size
        easting = easting - (easting % settings.CONTRIBUTION_TILE_SIZE)
        northing = northing - (northing % settings.CONTRIBUTION_TILE_SIZE)

        return self.get_or_create(
            *args, easting=easting, northing=northing, **kwargs)


class Tile(models.Model):
    """
    A square tile on the surface of the Earth.
    """

    # The bottom left coordinates
    easting = models.IntegerField()
    northing = models.IntegerField()

    country = models.ForeignKey(Country, related_name='tiles')
    geometry = models.MultiPolygonField(srid=settings.PROJECTION_SRID)

    objects = TileManager()

    def __unicode__(self):
        return '{easting},{northing}'.format(
            northing=self.northing, easting=self.easting)

    def save(self, *args, **kwargs):
        # If we are saving a new tile, we want to automatically
        # populate the geometry field
        if not self.geometry:
            # Create a box starting with the coordinates provided
            # at the bottom left
            points = [
                ProjectedPoint(self.easting, self.northing),
                ProjectedPoint(
                    self.easting + settings.CONTRIBUTION_TILE_SIZE,
                    self.northing,
                ),
                ProjectedPoint(
                    self.easting + settings.CONTRIBUTION_TILE_SIZE,
                    self.northing + settings.CONTRIBUTION_TILE_SIZE,
                ),
                ProjectedPoint(
                    self.easting,
                    self.northing + settings.CONTRIBUTION_TILE_SIZE,
                ),
                ProjectedPoint(self.easting, self.northing),
            ]

            self.geometry = ProjectedMultiPolygon([ProjectedPolygon(points)])

        # Look up the nearest country if none is set
        if not self.country_id:
            self.country = Country.objects.nearest_to_point(
                self.geometry.centroid)

        return super(Tile, self).save(*args, **kwargs)
