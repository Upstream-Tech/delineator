"""
Performs a detailed, raster-based watershed delineation with `pysheds`,
but only inside of a *single* unit catchment.
This is my implementation of the *hybrid* method that I "invented" -- but which was actually
first described in a a paper by Djokic and Ye at the 1999 ESRI User Conference.
Raster-based delineation is slow and requires a lot of memory. So we only do the bare minimum,
and use vector data for the rest of the upstream watershed.
"""
import os
from typing import Optional
from numpy import floor, ceil
from shapely.geometry import Polygon, MultiPolygon
from shapely import wkb, ops
import numpy as np

import config
from delineator_utils.raster_plots import plot_mask, plot_accum, plot_flowdir, plot_streams, plot_clipped, plot_polys
from delineator_utils.util import get_largest

FLOW_DIR_PATH = os.getenv("FLOW_DIR_PATH")
assert FLOW_DIR_PATH
ACCUM_PATH = os.getenv("ACCUM_PATH")
assert ACCUM_PATH

def split_catchment(wid: str, basin: int, lat: float, lng: float, catchment_poly: Polygon,
                    bSingleCatchment: bool) -> (tuple[Optional[object], float, float]):
    """
    Performs the detailed pixel-scale raster-based delineation for a watershed.

    To efficiently delineate large watersheds, we only use raster-based methods in a small area,
    the size of a single unit catchment that is most downstream. This results in big
    savings in processing time and memory use, making it possible to delineate even large watersheds
    on a laptop computer.

    Args:
        wid: the watershed id, a string
        basin: 2-digit Pfafstetter code for the level 2 basin we're in (tells us what files to open)
        lat: latitude
        lng: longitude
        catchment_poly: a Shapely polygon; we'll use it to clip the flow accumulation raster to get an accurate snap
        bSingleCatchment: is the watershed small, i.e. there is only one unit catchment in it?
            If so, we'll use a lower snap threshold for the outlet.

    Returns:
        poly: a shapely polygon representing the part of the terminal unit catchment that is upstream of the
            outlet point
        lat_snap:  latitude of the outlet, snapped to the river centerline in the accumulation raster
        lng_snap: longitude of the outlet, snapped to the river centerline in the accumulation raster

    For HIGH PRECISION, we will discard the most downstream catchment
    polygon, and replace it with a more detailed delineation.
    For this, we will use a small piece of the flow direction raster
    that fully contains the terminal unit catchment's boundaries,
    and do a raster-based delineation.
    This finds all of the pixels in the unit catchments that contribute flow to our
    pour point. Then, we will convert that collection of pixels to a polygon,
    and merge it with the upstream unit catchment polygons.

    Read the flow direction raster, but use "Windowed Reading",
    where we only read in the portion
    of interest, surrounding our catchment. See:
    https://mattbartos.com/pysheds/file-io.html
    There is no need to read the whole file into memory, because we are only
    interested in delineating a watershed within our little most-downstream unit catchment.
    Upstream of that, we used vector-based data
    For the window, get the bounding box for our catchment
    a tuple with 4 floats: (Left, Bottom, Right, Top)
    Note pysheds lets you read in a rectangular portion (and not a portion based
    on polygon geometry. We will clip the accumulation raster with the unit catchment
    polygon in a separate step below. (Not a clip per se, but we will replace the values
    in cells that are outside the unit catchment with NaN. This way, these cells will be
    ignored during the "snap pour point" routine, and we will only find rivers that are
    inside our unit catchment. It took me a while to figure out this workflow, but it is
    the key to getting accurate results!
    """

    # Get a bounding box for the unit catchment
    bounds = catchment_poly.bounds
    bounds_list = [float(i) for i in bounds]

    # The coordinates of the bounding box edges that we get from the above query
    # do not correspond well with the edges of the grid pixels.
    # We need to round them to the nearest whole pixel and then
    # adjust them by a half-pixel width to get good results in pysheds.

    # Distance of a half-pixel
    halfpix = 0.000416667

    # Bounding box is xmin, ymin, xmax, ymax
    # round the elements DOWN, DOWN, UP, UP
    # The number 1200 is because the MERIT-Hydro rasters have 3 arsecond resolution, or 1/1200 of a decimal degree.
    # So we just multiply it by 1200, round up or down to the nearest whole number, then divide by 1200
    # to put it back in its regular units of decimal degrees. Then, since pysheds wants the *center*
    # of the pixel, not its edge, add or subtract a half-pixel width as appropriate.
    # This took me a while to figure out but was essential to getting results that look correct
    bounds_list[0] = floor(bounds_list[0] * 1200) / 1200 - halfpix
    bounds_list[1] = floor(bounds_list[1] * 1200) / 1200 - halfpix
    bounds_list[2] = ceil(bounds_list[2] * 1200) / 1200 + halfpix
    bounds_list[3] = ceil(bounds_list[3] * 1200) / 1200 + halfpix
    # The bounding box needs to be a tuple for pysheds.
    bounding_box = tuple(bounds_list)

    # Open the flow direction raster *using windowed reading mode*
    # if config.get("VERBOSE"): print(" using windowed reading mode with bounding_box = {}".format(repr(bounding_box)))

    # The pysheds documentation was not up-to-date. Seems there were some changes in the API
    # for the versions with and without the numba library (sgrid and pgrid)
    # The first line did not work, but the following does. Took ages to figure this out! :(
    # I think it had to do with when the developer added the ability to use numba, the code forked.
    # You can still use it without numba, but the code is older and has not evolved with the new stuff (?)
    # Anyhow, the old version worked better for me in my testing.
    # grid = Grid.from_raster(path=fdir_fname, data=fdir_fname, data_name="myflowdir", window=bounding_box,nodata=0)
    from pysheds.grid import Grid
    grid = Grid.from_raster(FLOW_DIR_PATH, window=bounding_box, nodata=0)

    # Now "clip" the rectangular flow direction grid even further so that it ONLY contains data
    # inside the bounaries of the terminal unit catchment.
    # This prevents us from accidentally snapping the pour point to a neighboring watershed.
    # This was especially a problem around confluences, but this step seems to fix it.
    # (Seems I had to first convert it to hex format to get this to work...)
    hexpoly = catchment_poly.wkb_hex
    poly = wkb.loads(hexpoly, hex=True)
    # coerce this into a single-part polygon, in case the geometry is a MultiPolygon
    poly = get_largest(poly)

    # Fix any holes in the polygon by taking the exterior coordinates.
    # One of the annoyances of working with GeoPandas and pysheds is that you have
    # to constantly switch back and forth between Polygons and MultiPolygons...
    filled_poly = Polygon(poly.exterior.coords)

    # It needs to be of type MultiPolygon to work with rasterio apparently
    multi_poly = MultiPolygon([filled_poly])
    polygon_list = list(multi_poly.geoms)

    # Convert the polygon into a pixelized raster "mask".
    mymask = grid.rasterize(polygon_list)
    # grid.add_gridded_data(mymask, data_name="mymask", affine=grid.affine, crs=grid.crs, shape=grid.shape)

    # LOAD Flow Direction Grid
    fdir = grid.read_raster(FLOW_DIR_PATH, window=bounding_box, nodata=0)

    # Not clear if this this step was unnecessary, but it makes the plots look nicer
    m, n = grid.shape
    for i in range(0, m):
        for j in range(0, n):
            if int(mymask[i, j]) == 0:
                fdir[i, j] = 0

    # Plot the mask that I created from rasterized vector polygon
    if config.get("PLOTS"):
        plot_mask(mymask, catchment_poly, lat, lng, wid)

    # MERIT-Hydro flow direction uses the ESRI standard for flow direction...
    dirmap = (64, 128, 1, 2, 4, 8, 16, 32)

    # Plot the flow-direction raster, for debugging
    if config.get("PLOTS"):
        plot_flowdir(fdir, lat, lng, wid, dirmap, catchment_poly)

    # if config.get("VERBOSE"): print("Snapping pour point")

    # Open the accumulation raster, again using windowed reading mode.
    acc = grid.read_raster(ACCUM_PATH, data_name="acc", window=bounding_box, window_crs=grid.crs, nodata=0)

    # MASK the accumulation raster to the unit catchment POLYGON. Set any pixel that is not
    # in 'mymask' to zero. That way, the pour point will always snap to a grid cell that is
    # inside our polygon for the unit catchment, and will not accidentally snap
    # to a neighboring watershed. It took me a bunch of experimenting to realize
    # that this is the key to getting good results in small watersheds, especially
    # when there are other streams nearby.
    # The approach I used (looping over every pixel in the grid) is simple but a little hackish.
    # Would be better implemented as a method in pysheds.
    m, n = grid.shape
    for i in range(0, m):
        for j in range(0, n):
            if int(mymask[i, j]) == 0:
                acc[i, j] = 0

    # Snap the outlet to the nearest stream. This function depends entirely on the threshold
    # that you set for how minimum number of upstream pixels to define a waterway.
    # If the user is looking for a small headwater stream, we can use a small number.
    # In this case, there will be only one unit catchment in the watershed.
    # In most other circumstances (num unit catchments > 1), a much larger value gives better results.
    # The values here work OK, but I did not test very extensively...
    # Using a minimum value like 500 prevents the script from finding little tiny watersheds.
    if bSingleCatchment:
        numpixels = config.get("THRESHOLD_SINGLE")
    else:
        # Case where there are 2 or more unit catchments in the watershed
        # setting this value too low causes incorrect results and weird topology problems in the output
        numpixels = config.get("THRESHOLD_MULTIPLE")

    # if config.get("VERBOSE"): print("Using threshold of {} for number of upstream pixels.".format(numpixels))

    # Snap the pour point to a point on the accumulation grid where accum (# of upstream pixels)
    # is greater than our threshold
    streams = acc > numpixels
    xy = (lng, lat)
    try:
        [lng_snap, lat_snap] = grid.snap_to_mask(streams, xy)  # New version does not give you the snap distance.
    except Exception as e:
        if config.get("VERBOSE"): print(f"Could not snap the pour point. Error: {e}")
        return None, None, None

    # Plot the accumulation grid, for debugging
    if config.get("PLOTS"):
        plot_accum(acc, lat, lng, lat_snap, lng_snap, wid, catchment_poly)

    # Plot the streams!
    if config.get("PLOTS"):
        plot_streams(streams, catchment_poly, lat, lng, lat_snap, lng_snap, wid, numpixels)

    # Finally, here is the raster based watershed delineation with pysheds!
    if config.get("VERBOSE"): print(f"Delineating catchment {wid}")
    try:
        catch = grid.catchment(fdir=fdir,
                               x=lng_snap,
                               y=lat_snap,
                               dirmap=dirmap,
                               xytype='coordinate',
                               recursionlimit=15000)

        # Clip the bounding box to the catchment
        # Seems optional, but turns out this line is essential.
        grid.clip_to(catch)
        clipped_catch = grid.view(catch, dtype=np.uint8)
    except Exception as e:
        if config.get("VERBOSE"): print(f"ERROR: something went wrong during pysheds grid.catchment(). Error: {e}")
        return None, lng_snap, lat_snap

    # Convert high-precision raster subcatchment to a polygon using pysheds method .polygonize()
    # if config.get("VERBOSE"): print("Converting to polygon")
    shapes = grid.polygonize(clipped_catch)

    # The output from pysheds is creating MANY shapes.
    # Dissolve them together with the unary union operation in shapely
    shapely_polygons = []

    shape_count = 0

    # The snapped vertices look better if we nudge them one half pixels
    lng_snap += halfpix
    lat_snap -= halfpix

    # Convert the result from pysheds into a list of shapely polygons
    for shape, value in shapes:
        pysheds_polygon = shape
        shape_count += 1
        # The pyshseds polygon can be converted to a shapely Polygon in this one-liner
        shapely_polygon = Polygon([[p[0], p[1]] for p in pysheds_polygon['coordinates'][0]])
        shapely_polygons.append(shapely_polygon)

    if shape_count > 1:
        # If pysheds returned multiple polygons, dissolve them using shapely's unary_union() function
        # Note that this can sometimes return a MultiPolygon, which we'll need to fix later
        result_polygon = ops.unary_union(shapely_polygons)

        if result_polygon.geom_type == "MultiPolygon":
            if config.get("PLOTS"):
                polygons = list(result_polygon.geoms)
                plot_polys(polygons, wid)

            result_polygon = get_largest(result_polygon)
    else:
        # If pysheds generated a single polygon, that is our answer
        result_polygon = shapely_polygons[0]

    if config.get("PLOTS"):
        # plot_catchment(catch, catchment_poly, result_polygon, lat, lng, lat_snap, lng_snap, wid, dirmap)
        plot_clipped(fdir, clipped_catch, catchment_poly, lat, lng, lat_snap, lng_snap, wid, result_polygon)

    return result_polygon, lat_snap, lng_snap
