# Set of routines for simplifying and consolidating river networks

import pickle
import networkx as nx
from upstream_delineator.py.plot_network import draw_graph
from upstream_delineator.py.graph_tools import calculate_shreve_stream_order, calculate_strahler_stream_order, prune_node
import numpy as np
from upstream_delineator.config import VERBOSE
from scipy.stats import skew
import matplotlib.pyplot as plt
from typing import Tuple

# Set to True to draw a bunch of network graphs. Mostly for debugging. Careful, they can get big for large networks
DRAW_NET_DIAGRAM = False
AREA_HISTOGRAMS = False


def show_area_stats(G: nx.Graph) -> None:
    """
    Print some stats summarizing the area of the subbasins in our graph
    :param G:
    :return: None
    """
    areas = [data['area'] for node, data in G.nodes(data=True)]

    # Step 3: Calculate statistics using NumPy
    n = len(areas)
    mean_area = np.mean(areas)
    median_area = np.median(areas)
    std_area = np.std(areas)
    cv = std_area / mean_area
    skewness = skew(areas)  # Gives a warning, but skew seems to work on a list just fine.

    # Print the results
    print("Summary statistics for subbasin areas:")
    print("n  | Median | Mean | Std. Dev. | CV  | Skew")
    print(f"{n},    {median_area:.3g},   {mean_area:.3g},    {std_area:.3g},   {cv:.3g},   {skewness:.3g}")

    # Show a histogram of the unit catchment areas; mostly for development
    if AREA_HISTOGRAMS:
        plt.hist(areas, bins='auto', edgecolor='black')
        plt.title('Histogram of Areas')
        plt.xlabel('Area')
        plt.ylabel('Frequency')
        plt.grid(True)
        plt.show()


def find_keys_by_value(dictionary: dict, value) -> list:
    """
    Finds all of the keys in a dictionary that have a given value.
    Kind of a reverse dictionary lookup. A little hackish.
    """
    keys = []
    for key, val in dictionary.items():
        if val == value:
            keys.append(key)
    return keys


def update_merges(merges_dict: dict, node, target) -> dict:
    """
    Update the merges dictionary as necessary whenever we add a new node: target pair

    :param merges_dict: a dictionary mapping node: target
    :param node: the node that is being pruned, or removed from the network
    :param target: the target node, to which the area will be merged
    :return: MERGES
    """
    if node in merges_dict.values():
        keys = find_keys_by_value(merges_dict, node)
        for key in keys:
            merges_dict[key] = target

    return merges_dict


def trim_clusters(G: nx.DiGraph, threshold_area: int or float, mergest_dict: dict, rivers2merge, rivers2delete):
    """
    Step #1, merge "leaves", or unit catchments with order = 1 with their downstream node,
    if the resulting area would not exceed the user's threshold for max. area.

    Here, the o's are removed.
    Any river reach polylines that were in these unit catchments will be deleted.
    The unit catchment polygon areas will be merged with x.
    o──┐
    o──x──    →   x──
    o──┘

    """
    leaves = [n for n, attr in G.nodes(data=True) if attr.get('shreve_order') == 1 and 'custom' not in attr]
    for leaf in leaves:
        if G.has_node(leaf):
            successors = list(G.successors(leaf))
            if len(successors) > 0:
                successor = list(G.successors(leaf))[0]
                neighbors = list(G.predecessors(successor))
                neighbors.remove(leaf)
                for neighbor in neighbors:
                    if 'custom' not in G.nodes[neighbor] and G.nodes[neighbor]['shreve_order'] == 1:
                        merged_area = G.nodes[leaf]['area'] + G.nodes[neighbor]['area']
                        if merged_area < threshold_area:
                            G.nodes[leaf]['area'] = merged_area
                            G.remove_node(neighbor)
                            # This step is essential; we are tracking merges, but
                            # what happens when we delete a node that was previously a target?
                            mergest_dict = update_merges(mergest_dict, neighbor, leaf)
                            mergest_dict[neighbor] = leaf
                            rivers2delete.append(neighbor)
                            if neighbor in rivers2merge:
                                rivers2delete.extend(rivers2merge[neighbor])
                                del rivers2merge[neighbor]

    G = calculate_shreve_stream_order(G)
    return G, mergest_dict, rivers2merge, rivers2delete


def collapse_stems(G: nx.DiGraph, max_area: int or float, merges_dict: dict, rivers2merge: dict
                   ) -> Tuple[nx.DiGraph, dict, dict]:
    """
    Step #2, merge "stem" nodes with their downstream neighbor.
    A stem node is one that has exactly 1 incoming edge, (and 1 outgoing edge)
    In other words it is NOT a junction.  Here, node x is removed.

    o──x──o   →   o────o

    The stem node x will be removed.
    Its catchment polygon area will be merged with the downstream node's catchment polygon
    Its river reach polyline will be merged with the downstream node's river reach.
    """

    stems1 = [node for node in G.nodes if G.in_degree(node) < 2 and 'custom' not in G.nodes[node]]

    # Sort the stem nodes from small to large so we remove small ones first, and end up with
    # more uniform subbasin sizes.
    stems = sorted(stems1, key=lambda node: G.nodes[node]['area'], reverse=True)

    for stem in stems:
        if G.has_node(stem):

            # Identify the downstream node.
            successors = list(G.successors(stem))

            # If the node has no successor, it is the terminal node, and we cannot merge it with anything.
            if len(successors) == 0:
                continue

            # In our network, there is never more than one downstream node.
            successor = successors[0]

            # Check whether the downstream node is a branch. If so, we cannot merge down.
            # The way we do this is to count the number of incoming nodes.
            if G.in_degree(successor) > 1:
                # Check whether the upstream node is custom... if not, we can merge the upstream node downward.
                predecessors = list(G.predecessors(stem))
                if len(predecessors) < 1:
                    continue
                predecessor = predecessors[0]
                if 'custom' in G.nodes[predecessor]:
                    continue
                successor = stem
                stem = predecessor

            merged_area = G.nodes[stem]['area'] + G.nodes[successor]['area']

            if merged_area < max_area:
                G.nodes[successor]['area'] = merged_area
                G = prune_node(G, stem)

                merges_dict = update_merges(merges_dict, stem, successor)
                merges_dict[stem] = successor

                if stem in rivers2merge:
                    node_list = rivers2merge[stem]
                    del rivers2merge[stem]
                else:
                    node_list = []

                if successor in rivers2merge:
                    rivers2merge[successor].append(stem)
                else:
                    rivers2merge[successor] = [stem]

                rivers2merge[successor].extend(node_list)

    G = calculate_shreve_stream_order(G)
    return G, merges_dict, rivers2merge


def prune_leaves(G: nx.DiGraph,
                 threshold_area: int or float,
                 merges_dict: dict,
                 rivers2merge: dict,
                 rivers2delete: list) -> Tuple[nx.DiGraph, dict, dict, list]:
    """
    Step #3, merges small solo "leaves" with their neighbors.
    Candidates are unit catchments with Shreve order = 1 AND area < threshold
    If they have exactly one neighbor, we can merge this unit catchment with its neighbor
    and delete its river reach.

    Here, node x is merged with its "neighbor," node 1

    o──┐                   o───┐
    o──(1)──o──o──    →    o──(1)──o──o──
        x───┘

    The polygon area of x is merged with (1)
    The river reach in x is deleted.
    """

    # This step will get us all the *candidate* leaves.
    # Those that have a shreve order = 1, area < threshold, and are NOT a custom node.
    leaves = [n for n, attr in G.nodes(data=True) if attr.get('shreve_order') == 1
              and attr.get('area') < threshold_area and 'custom' not in attr]

    # Actually, all of the candidate leaves are OK to merge?
    # Do not merge them with a downstream node if they have a neighbor
    for leaf in leaves:
        if G.has_node(leaf):
            successor = list(G.successors(leaf))[0]
            neighbors = list(G.predecessors(successor))
            if len(neighbors) == 2:
                neighbors.remove(leaf)
                neighbor = neighbors[0]
                merged_area = G.nodes[leaf]['area'] + G.nodes[neighbor]['area']
                if merged_area < threshold_area:
                    G.nodes[neighbor]['area'] = merged_area
                    G = prune_node(G, leaf)
                    merges_dict = update_merges(merges_dict, leaf, neighbor)
                    merges_dict[leaf] = neighbor
                    rivers2delete.append(leaf)
                    if leaf in rivers2merge:
                        rivers2delete.extend(rivers2merge[leaf])
                        del rivers2merge[leaf]

    G = calculate_shreve_stream_order(G)
    G = calculate_strahler_stream_order(G)
    return G, merges_dict, rivers2merge, rivers2delete


def last_merge(G: nx.DiGraph, threshold_area: int or float, merges_dict: dict, rivers2merge) \
        -> Tuple[nx.DiGraph, dict, dict]:
    """
    This final step in consolidating the river network graph,
    Merge stem nodes with their *upstream* neighbors where appropriate.
    Candidates nodes are those with only a single incoming edge (what I call stem nodes).
    If the combined area does not exceed the max. area threshold:

      - the node is removed from the network.
      - its catchment area is merged with the upstream node
      - its river reach polyline is merged with the upstream node's

    Basically, very similar to the function above `collapse_stems`, but merges in opposite
    direction. I found this was necessary as a final step
    to clean up any remaining small nodes that had been missed by the previous steps.

    Here, x is merged with (c)

    o───┐                o───┐
    o──(u)──x──o──  →    o──(u)──o

    """

    nodes1 = [node for node in G.nodes if G.in_degree(node) == 1]

    # Step 2: Sort these nodes by their 'area' attribute
    # Do this because we generally want to merge the small ones first, before the big ones,
    # so that are eventual node sizes are more uniform.
    nodes = sorted(nodes1, key=lambda node: G.nodes[node]['area'])

    for node in nodes:
        if G.has_node(node):

            # Identify the upstream node.
            predecessors = list(G.predecessors(node))

            # There should only be one upstream node, based on our selection above.
            predecessor = predecessors[0]
            if 'custom' in G.nodes[predecessor]:
                continue

            # Check what the merged area would be
            merged_area = G.nodes[node]['area'] + G.nodes[predecessor]['area']

            if merged_area < threshold_area:
                # Update the graph
                G.nodes[node]['area'] = merged_area
                G = prune_node(G, predecessor)

                # Update the subbasins merge info
                merges_dict = update_merges(merges_dict, predecessor, node)
                merges_dict[predecessor] = node

                # Update the river reach merge info
                if predecessor in rivers2merge:
                    node_list = rivers2merge[predecessor]
                    del rivers2merge[predecessor]
                else:
                    node_list = []

                if node in rivers2merge:
                    rivers2merge[node].append(predecessor)
                else:
                    rivers2merge[node] = [predecessor]

                rivers2merge[node].extend(node_list)

    G = calculate_shreve_stream_order(G)
    return G, merges_dict, rivers2merge


def consolidate_network(G: nx.DiGraph, threshold_area: float or int) -> Tuple[nx.DiGraph, dict, dict, list]:
    """
    Consolidates the nodes in a river network graph, merging nodes to make them larger, while
    preserving the overall shape and connectivity of the graph.
    Saves a record of nodes that have been merged in the dictionary MERGES that we will later
    use to dissolve their geometries (unit catchment polygons) in GeoPandas.

    I thought that this would be a solved problem in hydrology, but I could not
    find anything useful. So this is a novel, homebrew solution developed through trial and error!

    Inputs: G: graph of the river network. Nodes should have the attributes 'area' and 'length'
      MERGES: a dictionary, can be empty, or may already exist if we call this function more than once.

    Outputs:
        G, revised graph of the river network
          Usually, it will be smaller (fewer nodes) than the input graph

        MERGES: A dictionary containing information on what to do with the unit catchment geodata
          for deleted nodes. keys: id of deleted nodes. values: the id of the node which it is
          being merged into. The keys are unique. The values can be repeated many times.
          This information is used for the DISSOLVE operation for the unit catchment polygons.

        rivers2merge: Similar to above, a dictionary with information on how to merge river reach
        polylines. The key is the id of deleted nodes, and the value is the id of the node
        it will be merged with. Tracking these separately from unit catchments, because the merging
        rules are different! Again, relationship can be one to many.

        rivers2delete: In some cases, we simply discard the river reach polyline. This variable keeps
        track of those reaches that are flagged for deletion.

    """

    # Make sure that the network has the Shreve stream order attribute for every node
    G = calculate_shreve_stream_order(G)
    MERGES = {}
    rivers2merge = {}
    rivers2delete = []

    if DRAW_NET_DIAGRAM: draw_graph(G, filename='plots/test_net', title="Original Network")
    if VERBOSE:
        print(f"Consolidating river network. Max. subbasin area: {threshold_area}")
        print('Iteration #1')

    # Step 1, merge leaves with their downstream node
    G, MERGES, rivers2merge, rivers2delete = trim_clusters(G, threshold_area, MERGES, rivers2merge, rivers2delete)
    if DRAW_NET_DIAGRAM: draw_graph(G, filename='plots/test_pruned', title="Pruned Network after Step 1")

    # Step 2, merge stems
    G, MERGES, rivers2merge = collapse_stems(G, threshold_area, MERGES, rivers2merge)
    if DRAW_NET_DIAGRAM: draw_graph(G, filename='plots/test_step2', title="Stems merged, after Step 2")

    # Step #3, prune small solo leaves
    G, MERGES, rivers2merge, rivers2delete = prune_leaves(G, threshold_area, MERGES, rivers2merge, rivers2delete)
    if DRAW_NET_DIAGRAM: draw_graph(G, filename='plots/test_step4', title="Small solo leaves pruned, after Step 4")

    # Iterate through the consolidation steps until the network stops changing
    i = 1  # Counter to keep track of how many iterations we do
    while True:
        previous_num_nodes = G.number_of_nodes()
        G, MERGES, rivers2merge, rivers2delete = trim_clusters(G, threshold_area, MERGES, rivers2merge, rivers2delete)
        G, MERGES, rivers2merge = collapse_stems(G, threshold_area, MERGES, rivers2merge)
        G, MERGES, rivers2merge, rivers2delete = prune_leaves(G, threshold_area, MERGES, rivers2merge, rivers2delete)
        num_nodes = G.number_of_nodes()
        i += 1
        if VERBOSE: print(f"Iteration #{i}")

        # When there is no change in the number of nodes, we have converged on a solution and can stop iterating
        if num_nodes == previous_num_nodes:
            break

    # Final step, takes care of any remaining small stem nodes
    G, MERGES, rivers2merge = last_merge(G, threshold_area, MERGES, rivers2merge)

    if DRAW_NET_DIAGRAM:  draw_graph(G, filename='plots/test_step5', title="After iteration, Step 5")
    if VERBOSE: show_area_stats(G)

    return G, MERGES, rivers2merge, rivers2delete


def test():
    fname = '../output/iceland_graph.pkl'
    G = pickle.load(open(fname, "rb"))
    # Set a threshold for merging (e.g., 100 for the sum of areas)
    threshold_area = 500
    G, MERGES, rivers2merge, rivers2delete = consolidate_network(G, threshold_area=threshold_area)
    print(G.number_of_nodes())
    draw_graph(G, 'temp')

def test2():
    # Testing alt. version of step 2.
    fname = '../output/iceland_graph.pkl'
    G = pickle.load(open(fname, "rb"))
    MAX_AREA = 1500
    MERGES = {}
    rivers2merge = {}
    rivers2delete = []
    G, MERGES, rivers2merge = last_merge(G, MAX_AREA, MERGES, rivers2merge)
    draw_graph(G, 'temp')


if __name__ == "__main__":
    test()
