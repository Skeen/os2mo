SPDX-FileCopyrightText: 2018-2020 Magenta ApS
SPDX-License-Identifier: MPL-2.0
<template>
  <div :id="identifier">
    <mo-input-date-range
      v-model="entry.validity"
      :initially-hidden="validityHidden"
      :disabled-dates="{orgUnitValidity, disabledDates}"
    />

    <div class="form-row">
      <mo-it-system-picker
        class="select-itSystem"
        v-model="entry.itsystem"
        :preselected="entry.itsystem && entry.itsystem.uuid"
      />

      <mo-input-text
        class="input-itSystem"
        v-model="entry.user_key"
        :label="$t('input_fields.account_name')"
        required
      />
    </div>
  </div>
</template>

<script>
/**
 * A it system entry component.
 */
import MoItSystemPicker from '@/components/MoPicker/MoItSystemPicker'
import { MoInputText, MoInputDateRange } from '@/components/MoInput'
import MoEntryBase from './MoEntryBase'
import OrgUnitValidity from '@/mixins/OrgUnitValidity'

export default {
  mixins: [OrgUnitValidity],

  extends: MoEntryBase,
  name: 'MoItSystemEntry',
  components: {
    MoInputText,
    MoInputDateRange,
    MoItSystemPicker
  },

  watch: {
    /**
     * Whenever entry change, update newVal.
     */
    entry: {
      handler (newVal) {
        newVal.type = 'it'
        this.$emit('input', newVal)
      },
      deep: true
    }
  }
}
</script>
