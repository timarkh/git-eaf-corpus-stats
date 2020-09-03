import os
import json
import copy


class CorpusStats:
    """
    Contains methods for reading and processing basic statistics abot an ELAN corpus
    from JSON files prepared by a post-receive hook in the corpus repository.
    """

    def __init__(self, settings):
        self.corpora = copy.deepcopy(settings)
        for corpus in self.corpora:
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

    def calculate_stats(self):
        """
        Calculate statistics for each corpus based on the data read previously.
        """
        for corpus in self.corpora:
            corpus['total_sound_dur'] = 0
            if '#TOTAL_SOUND_DURATION' in corpus['dur_by_speaker']:
                corpus['total_sound_dur'] = corpus['dur_by_speaker']['#TOTAL_SOUND_DURATION']
                corpus['total_sound_dur_str'] = self.str_duration(corpus['total_sound_dur'])
                del corpus['dur_by_speaker']['#TOTAL_SOUND_DURATION']

            # Total transcribed duration for all speakers
            corpus['total_dur'] = sum(corpus['dur_by_speaker'][sp]
                                      for sp in corpus['dur_by_speaker'])
            # Total transcribed duration for informants
            corpus['inf_dur'] = sum(corpus['dur_by_speaker'][sp]
                                    for sp in corpus['dur_by_speaker']
                                    if not sp.lower().startswith('interviewer'))
            # Total token count for all speakers
            corpus['total_tok'] = 0
            corpus['total_tok_by_speaker'] = {}
            for sp in corpus['tok_by_speaker']:
                corpus['total_tok_by_speaker'][sp] = 0
                for tok in corpus['tok_by_speaker'][sp]:
                    corpus['total_tok'] += corpus['tok_by_speaker'][sp][tok]
                    corpus['total_tok_by_speaker'][sp] += corpus['tok_by_speaker'][sp][tok]
            # Total token count for informants
            corpus['inf_tok'] = 0
            for sp in corpus['tok_by_speaker']:
                if sp.lower().startswith('interviewer'):
                    continue
                for tok in corpus['tok_by_speaker'][sp]:
                    corpus['inf_tok'] += corpus['tok_by_speaker'][sp][tok]

            corpus['total_dur_str'] = self.str_duration(corpus['total_dur'])
            corpus['inf_dur_str'] = self.str_duration(corpus['inf_dur'])


if __name__ == '__main__':
    pass
