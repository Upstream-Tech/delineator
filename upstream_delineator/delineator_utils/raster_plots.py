"""
Plots of the raster analysis, for debugging mostly
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors, rc
from matplotlib.colors import LogNorm

from upstream_delineator import config

font = {'weight': 'normal',
        'size': 18}

rc('font', **font)


def plot_mask(mask, catchment_poly, lat, lng, wid):
    fig = plt.figure(figsize=(10, 8))
    fig.patch.set_alpha(0)
    numeric_array = mask.astype(int)
    plt.imshow(numeric_array, extent=mask.extent)
    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.scatter(x=lng, y=lat, c='red', edgecolors='black')
    plt.colorbar(label='Terminal Unit Catchment', fraction=0.06, pad=0.06)

    plt.title(f"Mask for the unit catchment for watershed id = {wid}")
    plt.savefig(f'{config.get("PLOTS_DIR")}/{wid}_raster_mask.jpg')
    plt.close(fig)


def plot_flowdir(fdir, lat, lng, wid, dirmap, catchment_poly):
    fig = plt.figure(figsize=(10, 8))
    fig.patch.set_alpha(0)
    plt.imshow(fdir, extent=fdir.extent, cmap='viridis', zorder=0, norm=LogNorm())
    boundaries = ([0] + sorted(list(dirmap)))
    plt.colorbar(boundaries=boundaries, values=sorted(dirmap), fraction=0.06, pad=0.06)
    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.scatter(x=lng, y=lat, c='red', edgecolors='black')
    plt.title(f'Flow direction grid for watershed id = {wid}')
    plt.savefig(f"{config.get('PLOTS_DIR')}/{wid}_raster_flowdir.jpg")
    plt.close(fig)


def plot_accum(acc, lat, lng, lat_snap, lng_snap, wid, catchment_poly):
    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_alpha(0)
    im = ax.imshow(acc, extent=acc.extent, zorder=0,
                   cmap='cubehelix',
                   norm=colors.LogNorm(1, acc.max())
                   )
    plt.colorbar(im, ax=ax, label='Upstream Cells', fraction=0.06, pad=0.06)
    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.scatter(x=lng, y=lat, c='red', edgecolors='black')
    plt.scatter(x=lng_snap, y=lat_snap, c='cyan', edgecolors='black')
    plt.title(f'Flow Accumulation Grid for watershed id = {wid}')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig(f"{config.get('PLOTS_DIR')}/{wid}_raster_accum.jpg")
    plt.close(fig)


def plot_streams(streams, catchment_poly, lat, lng, lat_snap, lng_snap, wid, numpixels):
    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_alpha(0)
    ax.imshow(streams, extent=streams.extent)
    plt.scatter(x=lng, y=lat, c='red', edgecolors='black')
    plt.scatter(x=lng_snap, y=lat_snap, c='cyan', edgecolors='black')
    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.title(f'Streams, defined by # upstream pixels > {numpixels}')
    plt.colorbar(label='Streams', fraction=0.06, pad=0.06)
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig(f"{config.get('PLOTS_DIR')}/{wid}_streams.jpg")
    plt.close(fig)


def plot_catchment(fdir, catchment_poly, result_polygon, lat, lng, lat_snap, lng_snap, wid, dirmap):
    """
    Needs work, doesn't look right.
    Plus, redundant with plot_clipped below
    """
    # Plot the catchment
    fig = plt.figure(figsize=(10, 8))
    fig.patch.set_alpha(0)  # Need this line to make the background pixels not show?

    boundaries = ([0] + sorted(list(dirmap)))

    plt.imshow(fdir, extent=fdir.extent, cmap='viridis', zorder=0, norm=LogNorm(), alpha=0.6)

    plt.colorbar(boundaries=boundaries, values=sorted(dirmap), fraction=0.06, pad=0.06)

    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.plot(*result_polygon.exterior.xy, color='black')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.scatter(x=lng, y=lat, c='red', edgecolors='black')
    plt.scatter(x=lng_snap, y=lat_snap, c='cyan', edgecolors='black', zorder=10)
    plt.title(f'Delineated Raster Catchment for watershed id = {wid}')
    plt.savefig(f"{config.get('PLOTS_DIR')}/{wid}_raster_catchment.jpg")
    plt.close(fig)


def plot_clipped(fdir, clipped_catch, catchment_poly, lat, lng, lat_snap, lng_snap, wid, result_polygon):
    # Plot the clipped catchment AND the polygonized result
    fig = plt.figure(figsize=(10, 8))
    fig.patch.set_alpha(0)
    dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
    boundaries = ([0] + sorted(list(dirmap)))
    clipped = np.where(clipped_catch, 1, np.nan)
    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.imshow(fdir, extent=fdir.extent,  cmap='viridis', zorder=0, norm=LogNorm(), alpha=0.6)
    plt.colorbar(label="Flow Direction", boundaries=boundaries, values=sorted(dirmap), fraction=0.06, pad=0.06)
    plt.plot(*catchment_poly.exterior.xy, color='red')
    plt.plot(*result_polygon.exterior.xy, color='black')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')

    plt.scatter(x=lng, y=lat, c='red', edgecolors='black')
    plt.scatter(x=lng_snap, y=lat_snap, c='cyan', edgecolors='black', zorder=10)
    plt.title('Clipped Catchment for watershed id = {}')
    plt.savefig(f"{config.get('PLOTS_DIR')}/{wid}_raster_catchment_and_poly.jpg")
    plt.close(fig)


def plot_polys(polygons: list, wid: str):
    """
    Plots a list of shapely polygons

    This was mostly to debug an issue where the subdivided downstream unit catchment
    is a MultiPolygon with more than one part. I needed to make sure that throwing out
    all but the largest parts was OK. After testing hundreds of watersheds, I found
    that the smaller parts were always one or two pixels in size, so I decided that using
    my get_largest() function was legitimate.

    """

    gdf = gpd.GeoDataFrame(columns=["id", "geometry"], crs='epsg:4326')
    n_polys = len(polygons)
    print(f"Results is a MULTIPOLYGON with {n_polys} parts. Check the plot")
    for i in range(0, n_polys):
        gdf.loc[i] = (i, polygons[i])

    [fig, ax] = plt.subplots(1, 1, figsize=(10, 8))
    plt.title(f"Subdivided downstream unit catchment for watershed id = '{wid}'"
              f"\nMultiPolygon with {n_polys} parts")

    # Plot each unit catchment with a different color
    for x in gdf.index:
        color = np.random.rand(3, )
        gdf.loc[[x]].plot(edgecolor='gray', color=color, ax=ax)

    plt.savefig(f"{config.get('PLOTS_DIR')}/{wid}_vector_catch_sub.jpg")
    plt.close(fig)
