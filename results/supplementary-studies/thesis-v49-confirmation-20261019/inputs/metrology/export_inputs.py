#!/usr/bin/env python3
"""Export small quality/metrology capsules from a preserved v49 campaign.

JSON scientific fields are retained; private absolute provenance paths are
replaced by explicit archive/external locators. NPZ bytes are copied unchanged.
The complete original path map is written only to --private-origin-registry,
outside the public inputs tree. This exporter never opens a raw ADC waveform,
prediction corpus, hardware adapter or network connection.
"""
import argparse
import hashlib
import json
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

    def sanitize(self, value, sibling_hash=None):
        if isinstance(value, dict):
            h = value.get('sha256') if re.fullmatch('[0-9a-f]{64}', str(value.get('sha256', ''))) else None
            return {k: self.sanitize(v, h) for k, v in value.items()
                    if k not in {'measurement_source_address', 'jetson_address', 'urecs_address'}}
        if isinstance(value, list):
            return [self.sanitize(v, sibling_hash) for v in value]
        if isinstance(value, str):
            # These strings are provenance only, never runnable dependencies.
            value = re.sub(r'/home/[^\s\"\'<>]*', lambda m: self.locator(m.group(), sibling_hash), value)
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

    def json(self, relative, value, origin=None, scope=None):
        clean = self.sanitize(value)
        raw = (json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
        binding = self.write(relative, raw)
        if origin:
            binding.update(origin)
            binding['transformation'] = 'scientific fields retained; private provenance locators projected'
            self.origins.append(dict(binding, scope=scope))
        return binding


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


def export_metrology(exporter):
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
    return exporter.json('metrology/index.json', {
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
            'Any later conversion correction requires a new versioned analysis of unchanged archived raw samples.']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-root', type=Path, required=True)
    parser.add_argument('--inputs-root', type=Path, required=True)
    parser.add_argument('--private-origin-registry', type=Path, required=True)
    args = parser.parse_args()
    try:
        args.private_origin_registry.resolve().relative_to(args.inputs_root.resolve())
    except ValueError:
        pass
    else:
        parser.error('The private origin registry must remain outside the public inputs tree')
    exporter = Exporter(args.campaign_root, args.inputs_root)
    quality = export_quality(exporter)
    metrology = export_metrology(exporter)
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
