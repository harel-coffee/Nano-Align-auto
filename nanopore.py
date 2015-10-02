#!/usr/bin/env python

from __future__ import print_function
import sys
from collections import namedtuple

import math
import scipy.io as sio
from scipy.interpolate import interp1d
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import numpy as np
from statsmodels.nonparametric.smoothers_lowess import lowess

Struct = namedtuple("Struct", ["open_current", "dwell", "pa_blockade", "trace"])


def get_data(filename):
    matrix = sio.loadmat(filename)["Struct"][0][0]
    event_traces = matrix[5]
    num_samples = event_traces.shape[1]

    events = []
    for sample_id in xrange(num_samples):
        dwell = float(matrix[2][0][sample_id])
        pa_blockade = float(matrix[3][0][sample_id])
        open_current = float(matrix[4][0][sample_id])

        trace = np.array(event_traces[:, sample_id])
        trace = -(trace - open_current) / open_current

        events.append(Struct(open_current, dwell, pa_blockade, trace))

    return events


def find_peaks(signal):
    WINDOW = 6
    deriv = np.zeros(len(signal) - 2)
    for i in xrange(len(deriv)):
        deriv[i] = (signal[i + 2] - signal[i]) / 2

    peaks = []
    for pos in xrange(WINDOW / 2, len(deriv) - WINDOW / 2):
        left = deriv[pos - WINDOW / 2: pos]
        right = deriv[pos: pos + WINDOW / 2]

        if all(x > 0 for x in left) and all(y < 0 for y in right):
            peaks.append(pos)

    return peaks


def theoretical_signal(peptide, window_size):
    VOLUMES = {"I": 0.1688, "F": 0.2034, "V": 0.1417, "L": 0.1679,
               "W": 0.2376, "M": 0.1708, "A": 0.0915, "G": 0.0664,
               "C": 0.1056, "Y": 0.2036, "P": 0.1293, "T": 0.1221,
               "S": 0.0991, "H": 0.1673, "E": 0.1551, "N": 0.1359,
               "Q": 0.1611, "D": 0.1245, "K": 0.1713, "R": 0.2021}

    signal = []
    for i in xrange(-window_size + 1, len(peptide) - 1):
        start, end = max(i, 0), min(i + window_size, len(peptide))
        volumes = np.array(map(VOLUMES.get, peptide[start:end]))
        value = math.sqrt(np.mean(volumes ** 2))
        #value = np.mean(volumes)
        signal.append(value)
    return signal


def get_acids_positions(peptide, window_size, plot_len):
    num_peaks = len(peptide) + window_size - 1
    peak_shift = float(plot_len) / (num_peaks - 1)
    initial_shift = (window_size - 1) * peak_shift / 2
    positions = []
    for aa in xrange(len(peptide)):
        positions.append(initial_shift + aa * peak_shift)
    return positions


def fill_gaps(alignment):
    res = np.zeros(len(alignment))
    open_gap = None if alignment[0] is not None else 0

    for i in xrange(len(alignment)):
        if open_gap is not None:
            if alignment[i] is not None:
                left, right = alignment[open_gap], alignment[i]
                if left is None:
                    left = right

                for j in xrange(open_gap, i + 1):
                    rate = (j - open_gap) / (i - open_gap)
                    res[j] = left + (right - left) * rate
                open_gap = None
        else:
            if alignment[i] is not None:
                res[i] = alignment[i]
            else:
                open_gap = i - 1
    return res


def fit_to_model(model_trace, event_trace):
    match = lambda p1, p2: 100 * (0.1 - abs(p1 - p2))
    score, aln_model, aln_event = glob_affine_gap(model_trace, event_trace,
                                                  -2, -1, match)
    filled_event = fill_gaps(aln_event)
    #print(len(aln_model), len(aln_event))
    #print(len([x for x in aln_model if x is None]))
    #print(len([x for x in aln_event if x is None]))
    trimmed_event = []
    for i in xrange(len(filled_event)):
        if aln_model[i] is not None:
            trimmed_event.append(filled_event[i])
    return trimmed_event


def alignment(signal_1, signal_2):
    match = lambda p1, p2: 100 * (0.1 - abs(p1 - p2))
    score, aln_1, aln_2 = glob_affine_gap(signal_1, signal_2, -4, -3, match)
    return score, fill_gaps(aln_1), fill_gaps(aln_2)


def glob_affine_gap(seq1, seq2, gap_open, gap_ext, match_fun):
    len1 = len(seq1)
    len2 = len(seq2)

    s_m = np.ones((len1 + 1, len2 + 1)) * float("-inf")
    s_x = np.ones((len1 + 1, len2 + 1)) * float("-inf")
    s_y = np.ones((len1 + 1, len2 + 1)) * float("-inf")
    b_m = np.zeros((len1 + 1, len2 + 1))
    b_x = np.zeros((len1 + 1, len2 + 1))
    b_y = np.zeros((len1 + 1, len2 + 1))
    s_m[0][0] = 0

    for i in xrange(len1 + 1):
        s_x[i][0] = gap_open + (i - 1) * gap_ext
        b_x[i][0] = 1
    for i in xrange(len2 + 1):
        s_y[0][i] = gap_open + (i - 1) * gap_ext
        b_y[0][i] = 2

    for i in xrange(1, len1 + 1):
        for j in xrange(1, len2 + 1):
            delta = match_fun(seq1[i - 1], seq2[j - 1])

            lst_m = [s_m[i - 1][j - 1] + delta,
                     s_x[i - 1][j - 1] + delta,
                     s_y[i - 1][j - 1] + delta]
            lst_x = [s_m[i - 1][j] + gap_open,
                     s_x[i - 1][j] + gap_ext,
                     s_y[i - 1][j] + gap_open]
            lst_y = [s_m[i][j - 1] + gap_open,
                     s_x[i][j - 1] + gap_open,
                     s_y[i][j - 1] + gap_ext]

            s_m[i][j] = max(lst_m)
            s_x[i][j] = max(lst_x)
            s_y[i][j] = max(lst_y)

            b_m[i][j] = lst_m.index(s_m[i][j])
            b_x[i][j] = lst_x.index(s_x[i][j])
            b_y[i][j] = lst_y.index(s_y[i][j])

    # backtracking
    all_mat = [s_m, s_x, s_y]
    i, j = len1, len2
    cur_mat = max(s_m, s_x, s_y, key=lambda x: x[len1][len2])
    score = cur_mat[len1][len2]
    res1, res2 = [], []
    while i > 0 or j > 0:
        if id(cur_mat) == id(s_m):
            res1.append(seq1[i - 1])
            res2.append(seq2[j - 1])
            cur_mat = all_mat[int(b_m[i][j])]
            i -= 1
            j -= 1
        elif id(cur_mat) == id(s_x):
            res1.append(seq1[i - 1])
            res2.append(None)
            cur_mat = all_mat[int(b_x[i][j])]
            i -= 1
        elif id(cur_mat) == id(s_y):
            res1.append(None)
            res2.append(seq2[j - 1])
            cur_mat = all_mat[int(b_y[i][j])]
            j -= 1
    return score, res1[::-1], res2[::-1]


def compare_events(events, prot, align, need_smooth):
    event_len = len(events[0])
    for event_1, event_2 in zip(events[:-1], events[1:]):
        if need_smooth:
            smooth_frac = float(1) / len(prot)
            event_1 = smooth(event_1, smooth_frac)
            event_2 = smooth(event_2, smooth_frac)

        median_1 = np.median(event_1)
        median_2 = np.median(event_2)
        std_1 = np.std(event_1)
        std_2 = np.std(event_2)

        #scaled_2 = map(lambda t: (t - median_2) * (median_1 / median_2) + median_1,
        #               event_2)
        scaled_1 = event_1 / median_1
        scaled_2 = event_2 / median_2

        if align:
            reduced_1 = map(lambda i: event_1[i], xrange(0, event_len, 10))
            reduced_2 = map(lambda i: scaled_2[i], xrange(0, event_len, 10))
            score, aligned_1, aligned_2 = alignment(reduced_1, reduced_2)
            plot_1 = aligned_1
            plot_2 = aligned_2
        else:
            plot_1 = scaled_1
            plot_2 = scaled_2

        plt.plot(plot_1)
        plt.plot(plot_2)
        plt.show()

def scale_events(main_signal, scaled_signal):
    median_main = np.median(main_signal)
    median_scaled = np.median(scaled_signal)
    std_main = np.std(main_signal)
    std_scaled = np.std(scaled_signal)

    #scale_guess = std_main / std_scaled
    scale_guess = median_main / median_scaled
    """
    obj_fun = (lambda (s, o_1, o_2):
                100 * sum((main_signal - (scaled_signal - o_1) * s + o_2) ** 2))
    res = minimize(obj_fun, [scale_guess, median_main, median_scaled])
    scale, offset_1, offset_2 = res.x
    return (scaled_signal - offset_1) * scale - offset_2
    """
    #return np.array(map(lambda x: (x - median_scaled) * scale_guess + median_main,
    #                    scaled_signal))
    return scaled_signal * scale_guess


def plot_blockades(events, prot, window, alignment, need_smooth):
    event_len = len(events[0])
    num_samples = len(events)

    model_volume = theoretical_signal(prot, window)
    model_grid = [i * event_len / (len(model_volume) - 1)
                  for i in xrange(len(model_volume))]
    #consensus = get_consensus(events)

    for event in events:
        if need_smooth:
            smooth_frac = float(1) / len(prot)
            event = smooth(event, smooth_frac)
        #peaks = find_peaks(event.trace)
        #print("Peaks detected: {0}".format(len(peaks)))

        interp_fun = interp1d(model_grid, model_volume, kind="cubic")
        model_interp = interp_fun(xrange(event_len))
        model_scaled = scale_events(event, model_interp)
        ###

        if alignment:
            reduced_trace = map(lambda i: event[i], xrange(0, event_len, 10))
            reduced_model = map(lambda i: model_scaled[i], xrange(0, event_len, 10))
            fitted_event = fit_to_model(reduced_model, reduced_trace)
            event_plot = fitted_event
            model_plot = reduced_model
        else:
            event_plot = event
            model_plot = model_scaled

        #plt.figure(dpi=160)
        plt.plot(event_plot, label="blockade")
        plt.plot(model_plot, label="model")

        # adding AAs text:
        event_mean = np.mean(event)
        acids_pos = get_acids_positions(prot, window, len(event_plot))
        for i, aa in enumerate(prot):
            plt.text(acids_pos[i], event_mean-0.1, aa, fontsize=10)

        # plt.plot(consensus, label="consenus")
        # yy = map(lambda p: event.trace[p], peaks)
        # plt.plot(peaks, yy, "ro")

        plt.legend()
        plt.show()


def get_consensus(events):
    consensus = None
    for event in events:
        if consensus is None:
            consensus = np.zeros(len(event.trace))
        consensus += event.trace
    return consensus / len(events)


def smooth(signal, frac):
    x = lowess(signal, range(len(signal)), return_sorted=False, frac=frac)
    return x


def get_averages(events, bin_size, flank, reverse):
    averages = []
    for event_bin in xrange(0, len(events) / bin_size):
        avg_signal = get_consensus(events[event_bin*bin_size:
                                   (event_bin+1)*bin_size])
        if reverse:
            avg_signal = avg_signal[::-1]
        averages.append(avg_signal[flank:-flank])

    return averages

#CCL5
#PROT = "SPYSSDTTPCCFAYIARPLPRAHIKEYFYTSGKCSNPAVVFVTRKNRQVCANPEKKWVREYINSLEMS"
#CXCL1
#PROT = "ASVATELRCQCLQTLQGIHPKNIQSVNVKSPGPHCAQTEVIATLKNGRKACLNPASPIVKKIIEKMLNSDKSN"
#H3N
PROT = "ARTKQTARKSTGGKAPRKQL"


WINDOW = 4
AVERAGE = 10
FLANK = 50
ALIGNMENT = False
REVERSE = True
SMOOTH = True


def main():
    if len(sys.argv) != 2:
        print("Usage: plot.py mat_file")
        return 1

    events = get_data(sys.argv[1])
    averages = get_averages(events, AVERAGE, FLANK, REVERSE)

    #plot_blockades(averages, PROT, WINDOW, ALIGNMENT, SMOOTH)
    compare_events(averages, PROT, ALIGNMENT, SMOOTH)


if __name__ == "__main__":
    main()
