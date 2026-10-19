#!/usr/bin/env python3
"""Export small quality/metrology capsules from a preserved v49 campaign.

Historical extraction utility for the preceding campaign/addendum snapshot.
Later operator confirmations and voltage-model provenance are maintained in
the authoritative public inputs, not regenerated from that older campaign.
Use reproduce.py with the current input manifest to render the publication;
this exporter is not the update path for those later documentation changes.

JSON scientific fields are retained; private absolute provenance paths are
replaced by explicit archive/external locators. NPZ bytes are copied unchanged.
The complete original path map is written only to --private-origin-registry,
outside the public inputs tree. This exporter never opens a raw ADC waveform,
prediction corpus, hardware adapter or network connection.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Exporter:
    def __init__(self, campaign, inputs):
        self.campaign = Path(campaign).resolve()
        self.inputs = Path(inputs).resolve()
        self.origins = []
        self.private_paths = {}

    def source(self, member):
        path = self.campaign / member
        raw = path.read_bytes()
        return json.loads(raw), {'origin_sha256': sha(raw), 'origin_archive_member': member,
                                 'origin_bytes': len(raw)}

    def locator(self, value, file_hash=None):
        path = Path(value)
        try:
            relative = path.relative_to(self.campaign)
        except ValueError:
            key = 'external-sha256:' + file_hash if file_hash else 'private-path-id:' + sha(value.encode())
        else:
            key = 'archive:' + relative.as_posix()
        self.private_paths[key] = value
        return key

    def addendum_locator(self, value, file_hash=None):
        """Project a follow-up path without assigning it to the old archive."""
        try:
            relative = Path(value).relative_to(self.campaign)
        except ValueError:
            key = 'external-sha256:' + file_hash if file_hash else 'private-path-id:' + sha(value.encode())
        else:
            key = 'campaign-member:' + relative.as_posix()
        self.private_paths[key] = value
        return key

    def sanitize(self, value, sibling_hash=None, *, locator=None, complete_paths=False):
        project = locator or self.locator
        if isinstance(value, dict):
            h = value.get('sha256') if re.fullmatch('[0-9a-f]{64}', str(value.get('sha256', ''))) else None
            return {k: self.sanitize(v, h, locator=locator, complete_paths=complete_paths) for k, v in value.items()
                    if k not in {'measurement_source_address', 'jetson_address', 'urecs_address'}}
        if isinstance(value, list):
            return [self.sanitize(v, sibling_hash, locator=locator, complete_paths=complete_paths) for v in value]
        if isinstance(value, str):
            if complete_paths and value.startswith('/home/'):
                return project(value, sibling_hash)
            # These strings are provenance only, never runnable dependencies.
            value = re.sub(r'/home/[^\s\"\'<>]*', lambda m: project(m.group(), sibling_hash), value)
            # Do not mistake package versions such as TensorRT 10.3.0.30 for IPs.
            value = re.sub(r'192\.168\.\d{1,3}\.\d{1,3}', '<private-source-address>', value)
        return value

    def write(self, relative, raw):
        path = self.inputs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('Refusing to replace different capsule bytes: ' + str(path))
        if not path.exists():
            path.write_bytes(raw)
        return {'path': relative, 'sha256': sha(raw), 'bytes': len(raw)}

    def json(self, relative, value, origin=None, scope=None, *, addendum=False):
        clean = self.sanitize(value, locator=self.addendum_locator if addendum else None,
                              complete_paths=addendum)
        raw = (json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
        binding = self.write(relative, raw)
        if origin:
            binding.update(origin)
            binding['transformation'] = 'scientific fields retained; private provenance locators projected'
            self.origins.append(dict(binding, scope=scope))
        return binding


def load_metrology_addendum(exporter, path=None, expected_sha256=None):
    """Read one explicitly bound new source; never call it an old archive member."""
    if path is None and expected_sha256 is None:
        return None
    if path is None or not re.fullmatch('[0-9a-f]{64}', expected_sha256 or ''):
        raise ValueError('Both metrology-addendum and its explicit SHA256 are required')
    path = Path(path).resolve()
    try:
        member = path.relative_to(exporter.campaign).as_posix()
    except ValueError as error:
        raise ValueError('The addendum source must have a campaign-relative identity') from error
    raw = path.read_bytes()
    if sha(raw) != expected_sha256:
        raise ValueError('Metrology addendum source SHA256 mismatch')
    value = json.loads(raw)
    if value.get('schema') != 'thesis-v49-ch0-joris-evidence-alignment-v1':
        raise ValueError('Unsupported metrology addendum schema')
    for key in ('nominal_scaling', 'channel_confirmation', 'evidence_status',
                'per_path_calibration_chain', 'claim_matrix', 'acceptance_alignment',
                'report_summary', 'invariant_scopes'):
        if key not in value:
            raise ValueError('Missing metrology addendum field: ' + key)
    nominal = value['nominal_scaling']
    params = nominal['design_parameters']
    expected = {'adc_reference_V': 2.048, 'adc_steps': 4096,
                'gain_V_per_V': 25, 'shunt_ohm': 0.020}
    for key, number in expected.items():
        observed = params.get(key)
        if type(observed) not in (int, float) or not math.isclose(observed, number, rel_tol=1e-12):
            raise ValueError('Unexpected documented nominal design parameter: ' + key)
    computed = params['adc_reference_V'] / (params['adc_steps'] * params['gain_V_per_V'] * params['shunt_ohm'])
    for key, expected in (('A_per_count', computed), ('mA_per_count', computed * 1000)):
        observed = nominal.get(key)
        if type(observed) not in (int, float) or not math.isclose(observed, expected, rel_tol=1e-12):
            raise ValueError('Nominal current increment disagrees with the documented design')
    channel = value['channel_confirmation']
    if type(channel.get('channel')) is not int or channel['channel'] != 0 or any(
            type(channel.get(key)) is not int or channel[key] != expected
            for key, expected in (('current_records_checked', 72), ('historical_records_checked', 42))):
        raise ValueError('The addendum must retain confirmed CH0 and the 70+2 checked captures')
    status = value['evidence_status']
    for key in ('nominal_1mA_per_count_explained', 'CH0_user_confirmed',
                'calibration_36_points_documented', 'separate_original_verification_documented',
                'rc_filter_77kHz_design_documented'):
        if status.get(key) is not True:
            raise ValueError('Documented addendum claim is not established: ' + key)
    for key in ('installed_firmware_build_bound', 'combined_physical_uncertainty_available'):
        if status.get(key) is not False:
            raise ValueError('This follow-up must preserve the remaining physical qualification gap: ' + key)
    if not isinstance(value['claim_matrix'], list) or not value['claim_matrix'] or any(
            not isinstance(row, dict) or row.get('status') not in {'closed', 'partially_clarified', 'open'}
            for row in value['claim_matrix']):
        raise ValueError('Explicit closed/partially_clarified/open claim status required')
    if not isinstance(value['per_path_calibration_chain'], list) or not value['per_path_calibration_chain']:
        raise ValueError('The existing per-path calibration chains must be retained')
    return {'value': value, 'origin': {
        'origin_addendum_member': member, 'origin_sha256': expected_sha256,
        'origin_bytes': len(raw), 'origin_reference': '../../METROLOGY_ADDENDUM_REFERENCE.json',
        'origin_scope': 'new CH0/Joris follow-up; not a member of the original edbd618a archive'}}


def apply_metrology_addendum(exporter, index, addendum):
    value = addendum['value']
    binding = exporter.json('metrology/ch0_joris_alignment.json', value,
        addendum['origin'], 'current CH0/Joris document and conversion-path alignment', addendum=True)
    for row in index['sources']:
        row['snapshot_role'] = 'previous_evidence_snapshot_before_CH0_Joris_alignment'
        row['current_interpretation_reference'] = binding['path']
    index['sources'].append({'source_id': 'ch0_joris_alignment',
        'scope': 'current follow-up; supersedes overbroad missing-design/channel/calibration statements',
        'snapshot_role': 'current_follow_up_evidence', **binding})
    index['ch0_joris_alignment'] = binding
    index['metrology_addendum_reference'] = '../../METROLOGY_ADDENDUM_REFERENCE.json'
    index['origin_archive_member_base'] = (
        'Only legacy origin_archive_member fields refer to the campaign root in the original archive. '
        'New origin_addendum_member fields use the separate metrology addendum reference.')
    index['follow_up_locator_scope'] = (
        'campaign-member: labels in the new capsule identify relative campaign paths; '
        'they do not assert membership of the original archive. Use the separate addendum reference.')
    status = index['current_status']
    status.pop('nominal_mA_interpretation_physically_confirmed', None)
    status.update({
        'operating_channel': value['channel_confirmation']['channel'],
        'CH0_user_confirmed': value['evidence_status']['CH0_user_confirmed'],
        'current_CH0_capture_records_checked': value['channel_confirmation']['current_records_checked'],
        'nominal_mA_per_ADC_count': value['nominal_scaling']['mA_per_count'],
        'nominal_mA_interpretation_design_documented': True,
        'historical_36_point_calibration_documented': True,
        'historical_separate_verification_documented': True,
        'differential_RC_77kHz_design_documented': True,
        'exact_RC_values_and_populated_board_binding_established': False,
        'ADC7953_vs_ADC7952_type_inconsistency_resolved': False,
        'installed_measurement_firmware_identity_bound': value['evidence_status']['installed_firmware_build_bound'],
        'payload': 'The documented 2.048-V/12-bit/20-mOhm/gain-25 design gives 1 mA per count. Raw ADC-code transmission is consistent with the nominal mA convention; it does not demonstrate a unit error. Installed component/range and calibration applicability remain separate bindings.',
        'power_boundary': 'The master thesis studies the Jetson-slot path. Its supply voltage is not assumed to be 5 V. Later CH0 full-system-input calibration and U(I) applicability must follow their own profiles and wiring evidence.',
        'per_path_calibration_chain_reference': binding['path'],
        'full_system_scale_factor_application': 'The setup-specific full-system factor s multiplies the completed power model. Historical Joris/Jetson power correction c remains a separate factor; neither denotes an additional ADC/current calibration. See each bound conversion path.',
        'historical_calibration': '36 load points across 0..3.5 A and a separate verification are documented for the original work. This does not retroactively provide a before/after drift or validation record for each October setup.',
        'filter': 'Approximately 77 kHz is a documented differential-RC design value before INA225, not its general component bandwidth or a newly measured complete-path transfer function.',
        'U_I_mapping': 'The later setup-specific full-system input models and original Jetson-slot U(I) boundary are distinct; exact board/supply/wiring applicability remains partial.',
        'combined_physical_energy_uncertainty': None,
        'fully_physically_qualified_energy_intervals': 0,
        'new_independent_calibration': False})
    index['minimum_remaining_evidence'] = [
        'Resolve ADS7953 versus ADS7952 using an existing unambiguous schematic/BOM or population record; retain the documented nominal design meanwhile.',
        'Bind the populated board/revision, active ADC range/reference, actual firmware build and exact CH0 circuit without treating channel confirmation as missing.',
        'Document the exact differential R/C topology and values and complete-path/timebase/alias limits; the 77-kHz design origin is already documented.',
        'Bind each existing current/voltage model and full-system factor to its supply, wiring, consumers and operating range; do not transfer the original slot U(I) model blindly.',
        'Retain the original separate verification while distinguishing missing October before/after drift, reference-instrument uncertainty and combined E/N uncertainty.',
        'Any future proven conversion correction requires a new versioned analysis of unchanged raw data; this documentation alignment changes no conversion factors.']
    return index


def export_quality(exporter):
    source_table, _ = exporter.source('tables/history_direct_quality_intervals.json')
    models = []
    for item in source_table['rows']:
        model = item['model']
        directory = 'evidence/history_quality/' + model + '/'
        result, result_origin = exporter.source(directory + 'result.json')
        plan, plan_origin = exporter.source(directory + 'frozen_plan.json')
        raw = (exporter.campaign / directory / 'absolute_full_split_bootstrap_values.npz').read_bytes()
        assert sha(raw) == result['bootstrap_values_sha256']
        assert plan_origin['origin_sha256'] == result['plan_sha256']
        assert result['n_images'] == plan['seed_schema']['n'] == 5000
        assert result['B'] == plan['seed_schema']['B'] == 1000
        assert result['seed'] == plan['seed']
        prefix = 'quality/' + model + '/'
        r = exporter.json(prefix + 'result.json', result, result_origin, 'existing direct paired offline analysis')
        p = exporter.json(prefix + 'frozen_plan.json', plan, plan_origin, 'original frozen image/resampling plan')
        b = exporter.write(prefix + 'absolute_full_split_bootstrap_values.npz', raw)
        b.update(origin_sha256=sha(raw), origin_archive_member=directory + 'absolute_full_split_bootstrap_values.npz',
                 transformation='unchanged original NPZ bytes')
        exporter.origins.append(dict(b, scope='saved absolute full/split bootstrap values'))
        models.append({'model': model, 'result': r, 'plan': p, 'bootstrap': b})
    assert len(models) == 7 and len({m['model'] for m in models}) == 7
    return exporter.json('quality/index.json', {
        'schema': 'v49-confirmation-quality-inputs-v1', 'models': models,
        'scope': 'Table/percentile reproduction from an existing direct paired offline analysis of saved predictions; no new inference or prediction evaluation.',
        'provenance_paths_are_dependencies': False,
        'origin_archive_member_base': 'preserved campaign root inside the external delivery archive',
        'interval': 'paired split-minus-full ordinary percentile 2.5/97.5; NumPy linear interpolation',
        'selection_scope': 'previously selected winner pair; no simultaneous selection correction',
        'full_prediction_bootstrap_recomputation': 'Requires the unchanged archived prediction inputs and original evaluator; not performed by the small table reproducer.'})


def export_metrology(exporter, addendum=None):
    sources = []
    def capsule(name, member, scope, transform=lambda x: x):
        value, origin = exporter.source(member)
        binding = exporter.json('metrology/' + name, transform(value), origin, scope)
        sources.append({'source_id': name.removesuffix('.json'), 'scope': scope, **binding})
        return value
    candidate = capsule('candidate_firmware.json',
        'evidence/resume_20261018/metrology/candidate_firmware_metrology_review.json',
        'candidate source only; installation and physical payload units unproven',
        lambda x: {k: x[k] for k in ('schema','candidate_only','installed_firmware_identity_bound',
            'reviewed_extracted_source_bytes_match_candidate_archive','source_observations','source_claims',
            'observed_saved_payloads','interpretation','newly_closed_physical_review_points')})
    targeted = capsule('configuration_and_reference_gaps.json',
        'evidence/resume_20261018/metrology/targeted_electrical_followup.json',
        'saved setup/fit configuration; no physical board identity or independent reference certification',
        lambda x: {k: x[k] for k in ('schema','scope','setups','newly_closed_absolute_electrical_review_points',
            'physical_absolute_qualification','combined_physical_energy_uncertainty','new_independent_reference_acquired')})
    capsule('calibration_records.json', 'evidence/electrical/calibration_records.json',
        'historical fit points and own-channel idle observations; not independent held-out validation')
    capsule('physical_prerequisites.json', 'evidence/electrical/physical_prerequisites.json',
        'still missing physical reference, board/channel, timebase and filter evidence')
    capsule('uncertainty_model_historical.json', 'evidence/electrical/uncertainty_model.json',
        'historical model/Jacobian/covariance interpretation only; old missing-inner-marker list intentionally not republished as current status',
        lambda x: {k: x[k] for k in ('measurement_model','coefficients','current_scale_semantics','formula',
            'ratio_formula','shared_power_gain','current_gain','offset','block_covariance',
            'repeat_se_interpretation','combined_uncertainty_status','combined_uncertainty_value',
            'illustrative_5_percent_used_as_uncertainty','new_acquisition')})
    capsule('primary_reference_documents.json', 'evidence/electrical/primary_source_records.json',
        'manufacturer specifications do not identify the three installed measurement paths')
    capsule('primary_nominal_current_ranges.json',
        'evidence/resume_20261018/metrology/postcampaign_ranges_20261019T060248092718Z/ranges.json',
        'final primary S04 nominal ranges: 70 full captures, 68 admitted target intervals and boundary hulls; not calibration evidence',
        lambda x: {k: x[k] for k in ('schema','created_at_utc','accepted_logical_slots','planned_logical_slots',
            'cohort_complete','excluded_logical_slots_count','nominal_current_formula','interpretation',
            'domain_excursions_are_voltage_model_extrapolations_not_ADC_clipping','scopes',
            'physical_absolute_qualification','combined_physical_uncertainty','per_source')})
    capsule('supplement_nominal_current_ranges.json',
        'evidence/energy_supplement_20261019/electrical/post_supplement_ranges_20261019T081337605542Z/ranges_and_energy.json',
        'two separate completed supplements only; exact partial-cell nominal reintegration, not physical qualification',
        lambda x: {k: v for k, v in x.items() if k not in {'source_receipts'}})
    capsule('historical_b500_provenance.json', 'evidence/history_b500_audit.json',
        'nine historical stored_bounds; no verified original three replicates or exact invocation/seed',
        lambda x: {'source_archive': x['source_archive'], 'table_source': x['table_source'], 'rows': x['rows'],
            'physical_acquisitions_added': x['physical_acquisitions_added'],
            'release_functions': [{'archive_member': p['archive_member'], 'member_sha256': p['member_sha256'],
                'functions': [{k: f[k] for k in ('name','line_start','line_end','sha256')} for f in p['functions']]}
                for p in x['release_source_proof']]})
    capsule('version_and_precision_bindings.json', 'evidence/identity_versions_precision.json',
        'historical version nulls retained; current NPU/compiler observations are separate and do not establish measurement-board firmware',
        lambda x: {'schema': x['schema'], 'generated_at_utc': x['generated_at_utc'],
            'selected_count': x['selected_count'], 'historical_version_attribution_from_current': x['historical_version_attribution_from_current'],
            'interpretation_rules': x['interpretation_rules'],
            'entries': [{k: v for k, v in e.items() if k in {'uid','model','setup_id','backend','historical_python_version_recorded',
                'historical_runtime_package_versions','historical_compiler_package_versions','historical_firmware_version',
                'historical_version_status','historical_precision_identity','stage_precision','current_installed_separate'}} for e in x['entries']]})
    models = []
    for setup in ('orin_nx_deepx_m1_01','orin_nx_hailo10_01','orin_nx_hailo8_01'):
        member = 'evidence/electrical/new_acquisition_models/' + setup + '.json'
        value, origin = exporter.source(member)
        b = exporter.json('metrology/models/' + setup + '.json', value, origin,
            'unchanged historical coefficient values, conditional nominal payload/current/voltage convention')
        models.append({'setup_id': setup, **b})
    assert candidate['installed_firmware_identity_bound'] is False
    assert targeted['physical_absolute_qualification'] is False
    index = {
        'schema': 'v49-confirmation-metrology-inputs-v1', 'sources': sources, 'models': models,
        'provenance_paths_are_dependencies': False,
        'origin_archive_member_base': 'preserved campaign root inside the external delivery archive',
        'current_status': {
            'fully_physically_qualified_energy_intervals': 0, 'combined_physical_energy_uncertainty': None,
            'installed_measurement_firmware_identity_bound': False,
            'nominal_mA_interpretation_physically_confirmed': False,
            'unit_error_established_from_candidate': False, 'new_independent_calibration': False,
            'ADC_clipping_proven': False, 'ADC_clipping_excluded': False,
            'scope': '70 primary A, 68 primary conditional B plus two separate conditional B; no physical C qualification',
            'payload': 'Candidate forwards masked 12-bit SPI values without conversion; its installation is unproven. Neither a unit error nor the nominal mA convention is established.',
            'power_boundary': 'Upstream nominal 19-V full-system input and downstream 5-V module rail are different boundaries.',
            'filter': 'INA225 component bandwidth at gain 25 is 250 kHz; no retained complete-path evidence establishes the 77-kHz claim.',
            'historical_b500': 'Generic percentile functions were found; nine rows retain stored_bounds because original replicates and exact invocation/seed are unbound.',
            'historical_versions': 'Current package/NPU firmware observations are not retroactively assigned; measurement-source firmware is a separate identity.'},
        'minimum_remaining_evidence': [
            'Bind the actual measurement-board firmware/build and ADC register/payload configuration to board serial/revision, schematic/BOM and the requested input channel.',
            'Record populated shunt value/tolerance/temperature coefficient, amplifier gain, ADC Vref/full-scale, saturation treatment and upstream supply/consumer wiring.',
            'Obtain independent simultaneous DC voltage/current idle and representative high-load references before/after thermal exposure, with instrument serial/ranges/certificate/uncertainty, covering the used current range.',
            'Supply the actual filter topology/components or complete-path transfer function, and characterize actual ADC sampling period/drift.',
            'Retain offset, nonlinearity, session drift and channel covariance; unknown systematic uncertainty is not zero and is not divided by sample count.',
            'Any later conversion correction requires a new versioned analysis of unchanged archived raw samples.']}
    if addendum is not None:
        apply_metrology_addendum(exporter, index, addendum)
    return exporter.json('metrology/index.json', index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-root', type=Path, required=True)
    parser.add_argument('--inputs-root', type=Path, required=True)
    parser.add_argument('--private-origin-registry', type=Path, required=True)
    parser.add_argument('--metrology-addendum', type=Path)
    parser.add_argument('--metrology-addendum-sha256')
    args = parser.parse_args()
    try:
        args.private_origin_registry.resolve().relative_to(args.inputs_root.resolve())
    except ValueError:
        pass
    else:
        parser.error('The private origin registry must remain outside the public inputs tree')
    exporter = Exporter(args.campaign_root, args.inputs_root)
    addendum = load_metrology_addendum(exporter, args.metrology_addendum,
                                      args.metrology_addendum_sha256)
    quality = export_quality(exporter)
    metrology = export_metrology(exporter, addendum)
    private = {'schema': 'v49-confirmation-private-electrical-export-origins-v1',
        'source_campaign': str(exporter.campaign), 'public_inputs_root': str(exporter.inputs),
        'exporter_sha256': sha(Path(__file__).read_bytes()), 'source_and_public_bindings': exporter.origins,
        'private_locator_to_original_path': exporter.private_paths,
        'quality_index': quality, 'metrology_index': metrology,
        'hardware_or_network_operations': 0, 'raw_waveform_or_prediction_corpus_reads': 0,
        'original_source_writes': 0}
    args.private_origin_registry.parent.mkdir(parents=True, exist_ok=True)
    args.private_origin_registry.write_text(json.dumps(private, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'quality_index': quality, 'metrology_index': metrology,
                     'private_registry': str(args.private_origin_registry)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
