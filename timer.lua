obs            = obslua
source_name    = ""
total_seconds  = 0
timer_active   = false
start_time     = nil  -- タイマー開始時の os.time()
offset_seconds = 0    -- 一時停止前までの累積秒数

-- 表示の更新 (00:00 形式)
function update_text()
    local source = obs.obs_get_source_by_name(source_name)
    if source ~= nil then
        local minutes = math.floor(total_seconds / 60)
        local seconds = total_seconds % 60
        local text = string.format("%02d:%02d", minutes, seconds)

        local settings = obs.obs_data_create()
        obs.obs_data_set_string(settings, "text", text)
        obs.obs_source_update(source, settings)
        obs.obs_data_release(settings)
        obs.obs_source_release(source)
    end
end

-- os.time() 差分方式。OBSタイマーの発火遅延に依存しないため長時間運用でも正確。
function timer_callback()
    if start_time == nil then return end
    total_seconds = offset_seconds + (os.time() - start_time)
    update_text()
end

function script_load(settings)
    source_name = obs.obs_data_get_string(settings, "source_name")
    update_text()
end

function script_unload()
    obs.timer_remove(timer_callback)
    timer_active = false
end

function script_defaults(settings)
    obs.obs_data_set_default_string(settings, "source_name", "")
end

function script_update(settings)
    source_name = obs.obs_data_get_string(settings, "source_name")
end

-- スクリプトの設定 UI
function script_properties()
    local props = obs.obs_properties_create()
    local p = obs.obs_properties_add_list(props, "source_name", "表示するテキストソース", obs.OBS_COMBO_TYPE_EDITABLE, obs.OBS_COMBO_FORMAT_STRING)

    -- テキストソースの一覧を取得
    local sources = obs.obs_enum_sources()
    if sources ~= nil then
        for _, source in ipairs(sources) do
            local id = obs.obs_source_get_unversioned_id(source)
            if id == "text_ft2_source" or id == "text_gdiplus" then
                local name = obs.obs_source_get_name(source)
                obs.obs_property_list_add_string(p, name, name)
            end
        end
        obs.obs_source_list_release(sources)
    end

    obs.obs_properties_add_button(props, "start_button", "キックオフ / 再開", function()
        if not timer_active then
            start_time = os.time()
            obs.timer_add(timer_callback, 1000)
            timer_active = true
        end
    end)
    obs.obs_properties_add_button(props, "stop_button", "一時停止", function()
        if timer_active then
            offset_seconds = offset_seconds + (os.time() - start_time)
            obs.timer_remove(timer_callback)
            timer_active = false
        end
    end)
    obs.obs_properties_add_button(props, "reset_button", "リセット (00:00)", function()
        obs.timer_remove(timer_callback)
        timer_active   = false
        offset_seconds = 0
        total_seconds  = 0
        start_time     = nil
        update_text()
    end)
    return props
end
