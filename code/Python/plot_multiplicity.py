from __future__ import division
import numpy
import sys
from math import fabs
import glob, os, sys, re
import config
import utils
import parse_file
import pickle
import pandas

import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
from matplotlib.patches import Ellipse
import matplotlib.transforms as transforms

from sklearn.metrics import pairwise_distances
from skbio.stats.ordination import pcoa

from statsmodels.stats.multitest import multipletests
import statsmodels.formula.api as smf
import statsmodels.api as sm


numpy.random.seed(123456789)

def make_multiplicity_dict(phage_or_host_type = 'host'):

    reference_1 = "%sdspoIIE-ANC.gbk" % config.data_directory
    gene_data_1 = parse_file.parse_gene_list(reference_1)
    gene_names_1, gene_start_positions_1, gene_end_positions_1, promoter_start_positions_1, promoter_end_positions_1, gene_sequences_1, strands_1, genes_1, features_1, protein_ids_1 = gene_data_1

    reference_2 = "%sdelta6-ANC.gbk" % config.data_directory
    gene_data_2 = parse_file.parse_gene_list(reference_2)
    gene_names_2, gene_start_positions_2, gene_end_positions_2, promoter_start_positions_2, promoter_end_positions_2, gene_sequences_2, strands_2, genes_2, features_2, protein_ids_2 = gene_data_2
    #gene_names_1 = numpy.asarray(gene_names_1)

    gene_names_intersection = set(gene_names_1).intersection(set(gene_names_2))
    gene_names_union = set(gene_names_1).union(set(gene_names_2))
    mult_path = "%smultiplicity_dict_%s.pickle" % (config.data_directory, phage_or_host_type)
    metadata_dict = utils.get_sample_metadata_dict()

    if phage_or_host_type == 'host':
        subpop_type = 'revived_total'
    else:
        subpop_type = 'filtered_phage'

    multiplicity_dict = {}
    for seed_bank_type in  utils.seed_bank_types:
        for phage_treatment_type in utils.phage_treatment_types:

            exists_all = False
            for replicate in utils.replicates:
                exists, annotated_mapgd_dict = utils.load_annotated_breseq(phage_or_host_type, seed_bank_type, phage_treatment_type, subpop_type, replicate)

                if exists == False:
                    continue

                else:
                    exists_all = True

                replicate_name = '%s_%s_%d' % (seed_bank_type, phage_treatment_type, replicate)

                multiplicity_dict[replicate_name] = {}

                for position, position_dict in annotated_mapgd_dict.items():

                    gene = position_dict['gene']

                    if (gene == 'intergenic') or (gene == 'repeat'):
                        continue

                    if phage_or_host_type == 'host':
                        # ignore genes that aren't in both strains
                        if gene not in gene_names_intersection:
                            continue

                    if (position_dict['annotation'] == 'synonymous') or (position_dict['annotation'] == 'noncoding'):
                        continue

                    frequency_trajectory = position_dict['frequency_trajectory']

                    if sum(frequency_trajectory>0) < utils.min_n_non_zero_freqs:
                        continue

                    if gene not in multiplicity_dict[replicate_name]:
                        multiplicity_dict[replicate_name][gene] = 0

                    # LLN argument for taking the mean?
                    #frequency_trajectory_mean = max(frequency_trajectory)
                    #frequency_trajectory_mean = frequency_trajectory[-1]
                    #frequency_trajectory_mean = 10**numpy.mean(numpy.log10(frequency_trajectory[frequency_trajectory>0]))
                    frequency_trajectory_mean = numpy.median(frequency_trajectory[frequency_trajectory>0])

                    if frequency_trajectory_mean >= 0:
                        multiplicity_dict[replicate_name][gene] += frequency_trajectory_mean

            if exists_all == False:
                continue

            samples_all = utils.get_samples_from_metadata(phage_or_host_type, seed_bank_type, phage_treatment_type, subpop_type, 1)

            reference = metadata_dict[samples_all[0]]['reference']
            gene_data = parse_file.parse_gene_list(reference)
            gene_names, gene_start_positions, gene_end_positions, promoter_start_positions, promoter_end_positions, gene_sequences, strands, genes, features, protein_ids = gene_data
            position_gene_map, effective_gene_lengths, substitution_specific_synonymous_fraction = parse_file.create_annotation_map(reference=reference, gene_data=gene_data)
            # turn values to multiplicity
            mean_effective_gene_length = numpy.mean(list(effective_gene_lengths.values())[:-3])

            for replicate in utils.replicates:
                replicate_name = '%s_%s_%d' % (seed_bank_type, phage_treatment_type, replicate)
                if replicate_name not in multiplicity_dict:
                    continue
                replicate_genes = list(multiplicity_dict[replicate_name].keys())
                for replicate_gene in replicate_genes:
                    multiplicity_dict[replicate_name][replicate_gene] = multiplicity_dict[replicate_name][replicate_gene]*mean_effective_gene_length/effective_gene_lengths[replicate_gene]

    with open(mult_path, 'wb') as handle:
        pickle.dump(multiplicity_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)


def load_multiplicity_dict(phage_or_host_type):

    mult_path = "%smultiplicity_dict_%s.pickle" % (config.data_directory, phage_or_host_type)

    with open(mult_path, 'rb') as handle:
        mult_dict = pickle.load(handle)
    return mult_dict




def confidence_ellipse(x, y, ax, n_std=3.0, facecolor='none', **kwargs):
    """
    Create a plot of the covariance confidence ellipse of *x* and *y*.
    Parameters
    ----------
    x, y : array-like, shape (n, )
        Input data.
    ax : matplotlib.axes.Axes
        The axes object to draw the ellipse into.
    n_std : float
        The number of standard deviations to determine the ellipse's radiuses.
    Returns
    -------
    matplotlib.patches.Ellipse
    Other parameters
    ----------------
    kwargs : `~matplotlib.patches.Patch` properties
    """
    if x.size != y.size:
        raise ValueError("x and y must be the same size")

    cov = numpy.cov(x, y)
    pearson = cov[0, 1]/numpy.sqrt(cov[0, 0] * cov[1, 1])
    # Using a special case to obtain the eigenvalues of this
    # two-dimensionl dataset.
    ell_radius_x = numpy.sqrt(1 + pearson)
    ell_radius_y = numpy.sqrt(1 - pearson)
    ellipse = Ellipse((0, 0),
        width=ell_radius_x * 2,
        height=ell_radius_y * 2,
        facecolor=facecolor,
        **kwargs)

    # Calculating the stdandard deviation of x from
    # the squareroot of the variance and multiplying
    # with the given number of standard deviations.
    scale_x = numpy.sqrt(cov[0, 0]) * n_std
    mean_x = numpy.mean(x)

    # calculating the stdandard deviation of y ...
    scale_y = numpy.sqrt(cov[1, 1]) * n_std
    mean_y = numpy.mean(y)

    transf = transforms.Affine2D() \
        .rotate_deg(45) \
        .scale(scale_x, scale_y) \
        .translate(mean_x, mean_y)

    ellipse.set_transform(transf + ax.transData)
    return ax.add_patch(ellipse)



def corr_mult_pcoa_axes(phage_or_host_type, number_of_dimensions=2, iter=10000):

    mult_dict = load_multiplicity_dict('host')
    df = pandas.DataFrame.from_dict(mult_dict).T
    df = df.fillna(0)
    df = df/df.sum(axis=1)[:,None]
    df_index = df.index.values
    df_array = df.values
    df_gene_names = df.columns.values

    df_bc = pairwise_distances(df, metric='braycurtis')

    df_pcoa = pcoa(df_bc , number_of_dimensions=2)
    ord_matrix = df_pcoa.samples.values

    reference = "%sdspoIIE_GCF_001660525.1_ASM166052v1_genomic.gbff" % config.data_directory
    gene_data = parse_file.parse_gene_list(reference)
    gene_names, gene_start_positions, gene_end_positions, promoter_start_positions, promoter_end_positions, gene_sequences, strands, genes, features, protein_ids = gene_data
    position_gene_map, effective_gene_lengths, substitution_specific_synonymous_fraction = parse_file.create_annotation_map(reference=reference, gene_data=gene_data)
    gene_names = numpy.asarray(gene_names)
    genes = numpy.asarray(genes)

    annotation_dict = parse_file.get_gene_annotation_dict(reference)

    corrcoef_dict = {}

    for row_idx, row in enumerate(df_array.T):
        gene_name_row = df_gene_names[row_idx]

        corrcoef_dict[gene_name_row] = {}
        corrcoef_dict[gene_name_row]['pc1'] = {}
        corrcoef_dict[gene_name_row]['pc2'] = {}
        corrcoef_dict[gene_name_row]['pc1']['null'] = []
        corrcoef_dict[gene_name_row]['pc2']['null'] = []

        rho_pc1 = numpy.corrcoef(row, ord_matrix[:,0])[1,0]
        rho_pc2 = numpy.corrcoef(row, ord_matrix[:,1])[1,0]

        corrcoef_dict[gene_name_row]['pc1']['observed'] = rho_pc1
        corrcoef_dict[gene_name_row]['pc2']['observed']  = rho_pc2


    rho_max_dict = {}
    rho_max_dict['pc1'] = []
    rho_max_dict['pc2'] = []
    for i in range(iter):
        numpy.random.shuffle(ord_matrix)
        rho_1_all = []
        rho_2_all = []
        for row_idx, row in enumerate(df_array.T):
            gene_name_row = df_gene_names[row_idx]

            rho_pc1_null = numpy.corrcoef(row, ord_matrix[:,0])[1,0]
            rho_pc2_null = numpy.corrcoef(row, ord_matrix[:,1])[1,0]

            corrcoef_dict[gene_name_row]['pc1']['null'].append(rho_pc1_null)
            corrcoef_dict[gene_name_row]['pc2']['null'].append(rho_pc2_null)

            rho_1_all.append(rho_pc1_null)
            rho_2_all.append(rho_pc2_null)

        rho_max_dict['pc1'].append(max(numpy.absolute(rho_1_all)))
        rho_max_dict['pc2'].append(max(numpy.absolute(rho_2_all)))

    for pc in ['pc1', 'pc2']:

        rho_max_all = numpy.asarray(rho_max_dict[pc])

        rho_all = []
        p_value_all = []

        for row_idx, row in enumerate(df_array.T):
            gene_name_row = df_gene_names[row_idx]

            #null = numpy.asarray(corrcoef_dict[gene_name_row]['pc1']['null'])
            observed = corrcoef_dict[gene_name_row][pc]['observed']
            #p_value_1 = sum(numpy.absolute(null) >= numpy.absolute(observed))/ iter
            p_value = sum(numpy.absolute(rho_max_all) >= numpy.absolute(observed)) / iter

            rho_all.append(observed)
            p_value_all.append(p_value)

        #reject, pvals_corrected, alphacSidak, alphacBonf = multipletests(p_value_all, alpha=0.05, method='fdr_bh')
        rho_all = numpy.asarray(rho_all)
        p_value_all = numpy.asarray(p_value_all)

        #print(rho_all[(p_value_all<0.05)])
        idx_sort = numpy.argsort(rho_all)[::-1]

        df_gene_names_copy = numpy.copy(df_gene_names)

        rho_all = rho_all[idx_sort]
        p_value_all = p_value_all[idx_sort]
        df_gene_names_copy = df_gene_names_copy[idx_sort]


        rho_values_to_keep = rho_all[(p_value_all<0.05) & (numpy.absolute(rho_all) > 0.5)]
        p_values_to_keep = p_value_all[(p_value_all<0.05) & (numpy.absolute(rho_all) > 0.5)]
        gene_names_to_keep = df_gene_names_copy[(p_value_all<0.05) & (numpy.absolute(rho_all) > 0.5)]
        #genes_to_keep = genes[(p_value_all<0.05) & (numpy.absolute(rho_all) > 0.9)]

        output_filename = "%ssignificant_genes_%s.txt" % (config.data_directory, pc)

        header = ['Locus tag', 'Gene', 'Annotation', 'Correlatin', 'P-value']
        header = ", ".join(header)

        output_file = open(output_filename,"w")
        output_file.write(header)
        output_file.write("\n")
        for g_idx, g in enumerate(gene_names_to_keep):

            if g not in annotation_dict:
                annotation_g = ''
            else:
                annotation_g = annotation_dict[g]
            #if annotation_g == 'hypothetical protein':
            #    continue
            if g in gene_names:
                gene = genes[numpy.where(gene_names==g)[0][0]]
            else:
                gene = ''

            line = [g, gene, annotation_g, str(rho_values_to_keep[g_idx]), str(p_values_to_keep[g_idx])]
            line = ", ".join(line)
            output_file.write(line)
            output_file.write("\n")

        output_file.close()




def plot_pcoa_host():

    mult_dict = load_multiplicity_dict('host')
    df = pandas.DataFrame.from_dict(mult_dict).T
    df = df.fillna(0)
    df = df/df.sum(axis=1)[:,None]

    df_index = df.index.values

    df_bc = pairwise_distances(df, metric='braycurtis')

    df_pcoa = pcoa(df_bc , number_of_dimensions=2)
    ord_matrix = df_pcoa.samples
    ord_matrix.to_csv("%smult_pcoa_host.csv" % config.data_directory, sep=',')

    df.to_csv("%smult_host.csv" % config.data_directory, sep=',')

    fig, ax = plt.subplots(figsize=(4, 4))

    fig = plt.figure(figsize = (8, 4)) #
    fig.subplots_adjust(bottom= 0.15,  wspace=0.25)

    ax_pcoa = plt.subplot2grid((1, 2), (0, 0), colspan=1)
    ax_euc = plt.subplot2grid((1, 2), (0, 1), colspan=1)

    ax_pcoa.scatter(0, 0, marker='o', c='k', alpha=1, s=20, zorder=2)

    ax_pcoa.axhline(y=0, color='k', linestyle=':', alpha = 1, lw=1.5, zorder=1)
    ax_pcoa.axvline(x=0, color='k', linestyle=':', alpha = 1, lw=1.5, zorder=1)

    euc_distances_dict = {}
    for seed_bank_type in  utils.seed_bank_types:
        for phage_treatment_type in utils.phage_treatment_types:

            if seed_bank_type == 'long_seed_bank':
                edgecolor = 'k'
            else:
                edgecolor = 'grey'

            if phage_treatment_type == 'noPhage':
                facecolor = edgecolor
            else:
                facecolor = edgecolor

            seed_bank_phage_idx = numpy.asarray([numpy.where(df_index==e)[0][0] for e in df_index if '%s_%s' % (seed_bank_type, phage_treatment_type) in e])
            #ax.scatter(ord_matrix.values[seed_bank_phage_idx,0], ord_matrix.values[seed_bank_phage_idx,1], marker = utils.marker_dict[phage_treatment_type],
            #    edgecolors='#244162', c = utils.color_dict[seed_bank_type], alpha = 0.8, s = 120, zorder=4, label=utils.seed_bank_types_format_dict[seed_bank_type] + ', ' + utils.phage_treatment_types_format_dict[phage_treatment_type])

            ax_pcoa.scatter(ord_matrix.values[seed_bank_phage_idx,0], ord_matrix.values[seed_bank_phage_idx,1], marker = utils.marker_dict[phage_treatment_type],
                edgecolors=edgecolor,linewidth=2, facecolors=facecolor, alpha = 0.8, s = 120, zorder=4, label=utils.seed_bank_types_format_dict[seed_bank_type] + ', ' + utils.phage_treatment_types_format_dict[phage_treatment_type])

            confidence_ellipse(ord_matrix.values[seed_bank_phage_idx,0], ord_matrix.values[seed_bank_phage_idx,1], ax_pcoa, n_std=2, edgecolor=edgecolor, linestyle='--', lw=2, zorder=3)


            euc_distances = numpy.sqrt((ord_matrix.values[seed_bank_phage_idx,0]**2) + (ord_matrix.values[seed_bank_phage_idx,1]**2))

            #standard_error = numpy.std(euc_distances)/numpy.sqrt(len(euc_distances))
            #mean = numpy.mean(euc_distances)
            euc_distances_dict[(seed_bank_type, phage_treatment_type)] = euc_distances

            #euc_count += 1

    euc_all = []

    euc_count = 0
    for phage_treatment_type in utils.phage_treatment_types:
        for seed_bank_type in  utils.seed_bank_types:

            if seed_bank_type == 'long_seed_bank':
                edgecolor = 'k'
            else:
                edgecolor = 'grey'

            if phage_treatment_type == 'noPhage':
                facecolor = edgecolor
            else:
                facecolor = edgecolor


            euc_distances = euc_distances_dict[(seed_bank_type, phage_treatment_type)]

            standard_error = numpy.std(euc_distances)/numpy.sqrt(len(euc_distances))
            mean = numpy.mean(euc_distances)

            ax_euc.errorbar(euc_count, mean, yerr=standard_error, linestyle='-', c = edgecolor, marker= utils.marker_dict[phage_treatment_type], lw = 2.5, zorder=1)
            ax_euc.scatter(euc_count, mean, marker = utils.marker_dict[phage_treatment_type], edgecolors=edgecolor, linewidth=2, facecolors=facecolor, alpha = 1, s = 120, zorder=2)

            euc_count += 1

            for rep in range(len(euc_distances)):
                euc_all.append((phage_treatment_type, seed_bank_type, rep, euc_distances[rep]))


    ax_pcoa.set_xlabel('PCo 1 (' + str(round(df_pcoa.proportion_explained[0],3)*100) + '%)' , fontsize = 12)
    ax_pcoa.set_ylabel('PCo 2 (' + str(round(df_pcoa.proportion_explained[1]*100, 1)) + '%)' , fontsize = 12)
    ax_pcoa.legend(loc="lower right", fontsize=6, markerscale=0.6)


    ax_euc.set_ylabel('Euclidean distance from the ancestor' , fontsize = 11)

    ax_euc.set_xticks([0, 1, 2, 3])
    ax_euc.set_xticklabels(['With seed bank', 'No seed bank', 'With seed bank', 'No seed bank'], fontsize=7)

    ax_euc.set_xlim([-0.25, 3.25])

    ax_euc.text(0.22, -0.12, "With phage", fontsize=12, ha='center', va='center', transform=ax_euc.transAxes)
    ax_euc.text(0.78, -0.12, "No phage", fontsize=12, ha='center', va='center', transform=ax_euc.transAxes)

    ax_pcoa.text(-0.1, 1.03, utils.subplot_labels[0], fontsize=11, fontweight='bold', ha='center', va='center', transform=ax_pcoa.transAxes)
    ax_euc.text(-0.1, 1.03, utils.subplot_labels[1], fontsize=11, fontweight='bold', ha='center', va='center', transform=ax_euc.transAxes)


    # plot euclidean distances from origin
    fig_name = '%spcoa_host.png' % (config.analysis_directory)
    fig.savefig(fig_name, bbox_inches = "tight", pad_inches = 0.4, dpi = 600)
    plt.close()


    labels = ['phage', 'seedbank', 'replicate', 'euc']
    df = pandas.DataFrame.from_records(euc_all, columns=labels)
    lmod = smf.ols(formula='euc ~ phage + seedbank + phage:seedbank', data=df).fit()
    anova = sm.stats.anova_lm(lmod, typ=2)

    print(anova)

    #print(dir(anova))
    anova_array = anova.to_numpy()
    F_phage, F_seedbank, F_inter, F_resid = anova_array[:,2]

    #lmod_params = lmod.params.values

    phage_null = []
    seedbank_null = []
    inter_null = []
    iter = 10000
    for i in range(iter):

        df['euc_null'] = numpy.random.permutation(df.euc)
        lmod_null = smf.ols(formula='euc_null ~ phage + seedbank + phage:seedbank', data=df).fit()
        anova_null = sm.stats.anova_lm(lmod_null, typ=2)
        anova_null_array = anova_null.to_numpy()

        F_phage_null, F_seedbank_null, F_inter_null, F_resid_null = anova_null_array[:,2]

        phage_null.append(F_phage_null)
        seedbank_null.append(F_seedbank_null)
        inter_null.append(F_inter_null)

    phage_null = numpy.asarray(phage_null)
    seedbank_null = numpy.asarray(seedbank_null)
    inter_null = numpy.asarray(inter_null)

    p_value_phage = sum(phage_null > F_phage)/iter
    p_value_seedbank = sum(seedbank_null > F_seedbank)/iter
    p_value_inter = sum(inter_null > F_inter)/iter

    print("F-phage = ", F_phage, 'P = ', p_value_phage)
    print("F-seedbank = ", F_seedbank, 'P = ', p_value_seedbank)
    print("F-inter = ", F_inter, 'P = ', p_value_inter)







def plot_pcoa_phage():

    mult_dict = load_multiplicity_dict('phage')
    df = pandas.DataFrame.from_dict(mult_dict).T
    df = df.fillna(0)
    df = df/df.sum(axis=1)[:,None]

    phage_treatment_type = 'SPO1'

    df_index = df.index.values

    df_bc = pairwise_distances(df, metric='braycurtis')

    df_pcoa = pcoa(df_bc , number_of_dimensions=2)
    ord_matrix = df_pcoa.samples
    ord_matrix.to_csv("%smult_pcoa_phage.csv" % config.data_directory, sep=',')

    df.to_csv("%smult_phage.csv" % config.data_directory, sep=',')

    fig, ax = plt.subplots(figsize=(4, 4))

    for seed_bank_type in  utils.seed_bank_types:
        seed_bank_phage_idx = numpy.asarray([numpy.where(df_index==e)[0][0] for e in df_index if '%s_%s' % (seed_bank_type, phage_treatment_type) in e])
        ax.scatter(ord_matrix.values[seed_bank_phage_idx,0], ord_matrix.values[seed_bank_phage_idx,1], marker = utils.marker_dict[phage_treatment_type],
            edgecolors='#244162', c = utils.color_dict[seed_bank_type], alpha = 0.8, s = 120, zorder=4, label=utils.seed_bank_types_format_dict[seed_bank_type])
        confidence_ellipse(ord_matrix.values[seed_bank_phage_idx,0], ord_matrix.values[seed_bank_phage_idx,1], ax, n_std=2, edgecolor=utils.color_dict[seed_bank_type], linestyle='--', lw=3)


    ax.set_xlabel('PCo 1 (' + str(round(df_pcoa.proportion_explained[0]*100, 1)) + '%)' , fontsize = 12)
    ax.set_ylabel('PCo 2 (' + str(round(df_pcoa.proportion_explained[1],3)*100) + '%)' , fontsize = 12)

    ax.legend(loc="upper left", fontsize=6)

    fig_name = '%spcoa_phage.png' % (config.analysis_directory)
    fig.savefig(fig_name, bbox_inches = "tight", pad_inches = 0.4, dpi = 600)
    plt.close()





#make_multiplicity_dict('phage')
#make_multiplicity_dict('host')
#plot_pcoa_host()
#plot_pcoa_phage()

#corr_mult_pcoa_axes('host')
