import os
import json
import copy


MAX_FREQ_TOKENS = 100


class CorpusStats:
    """
    Contains methods for reading and processing basic statistics abot an ELAN corpus
    from JSON files prepared by a post-receive hook in the corpus repository.
    """

    def __init__(self, settings):
        self.corpora = copy.deepcopy(settings)
        for corpus in self.corpora:
            if not os.path.exists(corpus['stats_dir']):
                corpus['name'] += ' (FOLDER DOES NOT EXIST!)'
                corpus['dur_by_speaker'] = {'XXX': 0}
                corpus['tok_by_speaker'] = {'XXX': {'XXX': 0}}
                continue
            with open(os.path.join(corpus['stats_dir'], 'duration_by_speaker.json'),
                      'r', encoding='utf-8') as fIn:
                corpus['dur_by_speaker'] = json.load(fIn)
            with open(os.path.join(corpus['stats_dir'], 'tokens_by_speaker.json'),
                      'r', encoding='utf-8') as fIn:
                corpus['tok_by_speaker'] = json.load(fIn)
        self.calculate_stats()

    def str_duration(self, duration):
        """
        Present duration in a human-readable form.
        """
        totalDurHours = round(duration // 3600)
        totalDurMinutes = round((duration - totalDurHours * 3600) // 60)
        totalDurSeconds = round(duration % 60)
        return str(totalDurHours).zfill(2) + ':' + str(totalDurMinutes).zfill(2) + ':' + str(totalDurSeconds).zfill(2)

    def is_interviewer(self, speaker):
        """
        Based on speaker's code, determine if they are an interviewer.
        """
        if speaker.lower().startswith('interviewer'):
            return True
        return False

    def calculate_stats(self):
        """
        Calculate statistics for each corpus based on the data read previously.
        """
        for corpus in self.corpora:
            corpus['speakers'] = list(set(sp for sp in corpus['dur_by_speaker']) & set(sp for sp in corpus['tok_by_speaker']))
            corpus['informants'] = [sp for sp in corpus['speakers'] if not self.is_interviewer(sp)]

            corpus['total_sound_dur'] = 0
            if '#TOTAL_SOUND_DURATION' in corpus['dur_by_speaker']:
                corpus['total_sound_dur'] = corpus['dur_by_speaker']['#TOTAL_SOUND_DURATION']
                corpus['total_sound_dur_str'] = self.str_duration(corpus['total_sound_dur'])
                del corpus['dur_by_speaker']['#TOTAL_SOUND_DURATION']

            corpus['dur_by_speaker_str'] = {sp: self.str_duration(corpus['dur_by_speaker'][sp])
                                            for sp in corpus['dur_by_speaker']}

            # Total transcribed duration for all speakers
            corpus['total_dur'] = sum(corpus['dur_by_speaker'][sp]
                                      for sp in corpus['dur_by_speaker'])
            # Total transcribed duration for informants
            corpus['inf_dur'] = sum(corpus['dur_by_speaker'][sp]
                                    for sp in corpus['dur_by_speaker']
                                    if not self.is_interviewer(sp))

            # Total token count for all speakers
            corpus['total_tok'] = 0
            corpus['total_tok_by_speaker'] = {}
            for sp in corpus['tok_by_speaker']:
                corpus['total_tok_by_speaker'][sp] = 0
                for tok in corpus['tok_by_speaker'][sp]:
                    corpus['total_tok'] += corpus['tok_by_speaker'][sp][tok]
                    corpus['total_tok_by_speaker'][sp] += corpus['tok_by_speaker'][sp][tok]

            # Total token count for informants only
            corpus['inf_tok'] = 0
            for sp in corpus['tok_by_speaker']:
                if self.is_interviewer(sp):
                    continue
                for tok in corpus['tok_by_speaker'][sp]:
                    corpus['inf_tok'] += corpus['tok_by_speaker'][sp][tok]

            # Common frequency list of tokens
            corpus['tok_freq'] = {}
            for sp in corpus['tok_by_speaker']:
                for token in corpus['tok_by_speaker'][sp]:
                    if token not in corpus['tok_freq']:
                        corpus['tok_freq'][token] = corpus['tok_by_speaker'][sp][token]
                    else:
                        corpus['tok_freq'][token] += corpus['tok_by_speaker'][sp][token]
            corpus['freq_tokens'] = [token for token in sorted(corpus['tok_freq'],
                                                               key=lambda t: (-corpus['tok_freq'][t], t))][:MAX_FREQ_TOKENS]

            corpus['total_dur_str'] = self.str_duration(corpus['total_dur'])
            corpus['inf_dur_str'] = self.str_duration(corpus['inf_dur'])


if __name__ == '__main__':
    pass
